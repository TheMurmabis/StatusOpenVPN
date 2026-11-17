import io
import os

from flask import make_response, render_template, request, send_file

from src.ui.constants import (
    OPENVPN_SUBSCRIPTION_SLUG_PATTERN,
    OPENVPN_SUBSCRIPTION_TOKEN_PATTERN,
)
from src.ui.extensions import app
from src.ui.services.ovpn_subscription_service import (
    authorize_subscription_file,
    authorize_subscription_page,
    are_subscriptions_active,
    get_subscription_link_lifetime_seconds,
    get_subscription_link_state,
    public_profile_items,
    resolve_subscription_file,
    subscription_client_summary,
    subscription_display_name,
)
from src.ui.services.settings_service import read_settings
from src.ui.utils.wireguard_naming import wg_conf_short_filename, wg_qr_png_for_conf_path


def _request_ua_method():
    user_agent = ""
    if request.user_agent:
        user_agent = request.user_agent.string or ""
    return user_agent, request.method


def _subscribe_headers(response):
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "no-store"
    return response


_SUBSCRIPTION_ERROR_CONTENT = {
    "invalid": {
        "title": "Ссылка недействительна",
        "message": "Проверьте адрес или запросите новую ссылку у администратора.",
        "icon": "bi-link-45deg",
        "status": 404,
    },
    "expired": {
        "title": "Срок действия ссылки истёк",
        "message": "Запросите у администратора новую ссылку для подключения.",
        "icon": "bi-clock-history",
        "status": 410,
    },
    "revoked": {
        # Keep the public explanation generic while preserving the correct status.
        "title": "Ссылка недействительна",
        "message": "Ссылка больше не действует. Запросите новую у администратора.",
        "icon": "bi-link-45deg",
        "status": 410,
    },
    "disabled": {
        "title": "Публичные ссылки недоступны",
        "message": "Попробуйте открыть ссылку позже или обратитесь к администратору.",
        "icon": "bi-cloud-slash",
        "status": 503,
    },
}


def _subscribe_error(state="invalid"):
    error = _SUBSCRIPTION_ERROR_CONTENT.get(
        state, _SUBSCRIPTION_ERROR_CONTENT["invalid"]
    )
    response = make_response(
        render_template(
            "ovpn/ovpn_subscribe.html",
            not_found=True,
            error_title=error["title"],
            error_message=error["message"],
            error_icon=error["icon"],
            display_name="",
            token="",
            items=[],
            summary=None,
            start_family="openvpn",
        ),
        error["status"],
    )
    return _subscribe_headers(response)


def _failed_subscription_state(token):
    if not are_subscriptions_active():
        return "disabled"
    state = get_subscription_link_state(token)
    return state if state in {"expired", "revoked"} else "invalid"


def _authorized_choice(token, slug):
    if not are_subscriptions_active():
        return None
    token = (token or "").strip()
    slug = (slug or "").strip().lower()
    if not OPENVPN_SUBSCRIPTION_TOKEN_PATTERN.fullmatch(token):
        return None
    if not OPENVPN_SUBSCRIPTION_SLUG_PATTERN.fullmatch(slug):
        return None
    user_agent, method = _request_ua_method()
    record = authorize_subscription_file(token, user_agent, method)
    if not record:
        return None
    return resolve_subscription_file(
        record.get("client_name"), slug, record.get("telegram_id")
    )


def _wg_download_name(choice):
    path = choice.get("path") or ""
    shorten = bool(read_settings().get("shorten_wg_filenames", False))
    if shorten and path:
        return wg_conf_short_filename(path)
    return choice.get("filename") or os.path.basename(path)


@app.route("/s/<token>")
def ovpn_subscribe_page(token):
    if not are_subscriptions_active():
        return _subscribe_error("disabled")
    token = (token or "").strip()
    if not OPENVPN_SUBSCRIPTION_TOKEN_PATTERN.fullmatch(token):
        return _subscribe_error()
    link_state = get_subscription_link_state(token)
    if link_state != "active":
        return _subscribe_error(link_state)

    user_agent, method = _request_ua_method()
    record = authorize_subscription_page(token, user_agent, method)
    if not record:
        return _subscribe_error(_failed_subscription_state(token))

    client_name = record.get("client_name")
    temporary = bool(record.get("temporary", True))
    lifetime_seconds = get_subscription_link_lifetime_seconds()
    expires_at = None
    if temporary and record.get("expires_at") is not None:
        expires_at = int(float(record["expires_at"]) * 1000)
    items = public_profile_items(client_name, record.get("telegram_id"))
    summary = subscription_client_summary(client_name)
    has_openvpn = any((item.get("family") or "openvpn") == "openvpn" for item in items)
    start_family = "openvpn" if (not items or has_openvpn) else "wireguard"
    response = make_response(
        render_template(
            "ovpn/ovpn_subscribe.html",
            not_found=False,
            display_name=subscription_display_name(client_name),
            token=token,
            items=items,
            temporary=temporary,
            expires_at=expires_at,
            link_lifetime_minutes=lifetime_seconds // 60,
            summary=summary,
            start_family=start_family,
        )
    )
    return _subscribe_headers(response)


@app.route("/s/<token>/<slug>.ovpn")
def ovpn_subscribe_file(token, slug):
    choice = _authorized_choice(token, slug)
    if not choice or (choice.get("family") or "openvpn") != "openvpn":
        return _subscribe_error(_failed_subscription_state(token))

    response = send_file(
        choice["path"],
        mimetype="application/x-openvpn-profile",
        as_attachment=False,
        download_name=choice["filename"],
        max_age=0,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return _subscribe_headers(response)


@app.route("/s/<token>/<slug>.conf")
def wg_subscribe_file(token, slug):
    choice = _authorized_choice(token, slug)
    if not choice or choice.get("family") != "wireguard":
        return _subscribe_error(_failed_subscription_state(token))

    response = send_file(
        choice["path"],
        mimetype="text/plain",
        as_attachment=True,
        download_name=_wg_download_name(choice),
        max_age=0,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return _subscribe_headers(response)


@app.route("/s/<token>/<slug>.png")
def wg_subscribe_qr(token, slug):
    choice = _authorized_choice(token, slug)
    if not choice or choice.get("family") != "wireguard":
        return _subscribe_error(_failed_subscription_state(token))

    try:
        png_data = wg_qr_png_for_conf_path(choice["path"])
    except (FileNotFoundError, OSError, RuntimeError):
        return _subscribe_error()

    response = send_file(
        io.BytesIO(png_data),
        mimetype="image/png",
        as_attachment=False,
        download_name="wireguard-qr.png",
        max_age=0,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return _subscribe_headers(response)
