import io
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone

from flask import jsonify, request, send_file
from flask_login import current_user, login_required

from src.ui.constants import CLIENT_NAME_PATTERN, CLIENT_SH_PATH
from src.ui.extensions import app
from src.ui.services.openvpn_service import (
    ensure_client_connect_ban_check_block,
    get_all_openvpn_clients,
    kick_openvpn_client,
    read_banned_clients,
    run_openvpn_add_or_renew_client,
    write_banned_clients,
)
from src.ui.services.ovpn_subscription_service import (
    create_subscription_url,
    are_subscriptions_active,
    subscriptions_unavailable_message,
    revoke_client_subscription,
    set_client_subscription_temporary,
    set_client_subscription_enabled,
    get_client_subscription_temporary,
    get_client_subscription_enabled,
    get_client_subscription_url,
    get_subscription_service_warnings,
)
from src.ui.services.settings_service import (
    get_subscription_link_lifetime_minutes,
    get_vpn_client_protocols,
    read_settings,
    set_vpn_client_protocols,
)
from src.ui.services.scheduled_block_service import (
    cancel_scheduled_openvpn_block,
    schedule_openvpn_block,
)
from src.ui.utils.openvpn_naming import (
    list_openvpn_ovpn_paths_for_client,
    ovpn_profile_label,
)
from src.ui.utils.wireguard_naming import (
    list_wg_conf_paths_for_client,
    wg_client_name_param_ok,
    wg_conf_path_is_allowed,
    wg_conf_profile_label,
    wg_conf_short_filename,
    wg_qr_png_for_conf_path,
)
from src.tg_bot.audit import log_action


_SUBSCRIPTION_PROTOCOL_KEYS = (
    "openvpn_vpn", "openvpn_antizapret", "openvpn_default",
    "openvpn_tcp", "openvpn_udp", "wireguard_vpn",
    "wireguard_antizapret", "wireguard_wg", "wireguard_am",
)


def _parse_scheduled_block_time(raw_value):
    raw = (raw_value or "").strip()
    if not raw:
        return None, "Укажите дату и время блокировки."
    try:
        scheduled_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None, "Некорректная дата блокировки."
    if scheduled_at.tzinfo is None:
        return None, "Не указан часовой пояс даты блокировки."
    scheduled_at = scheduled_at.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if scheduled_at <= now + timedelta(seconds=30):
        return None, "Дата блокировки должна быть в будущем."
    if scheduled_at > now + timedelta(days=3650):
        return None, "Дата блокировки не может быть позже чем через 10 лет."
    return scheduled_at, ""


def _subscription_protocol_selection_error(protocols, has_openvpn, has_wireguard):
    families = (
        (
            has_openvpn,
            "OpenVPN",
            ("openvpn_vpn", "openvpn_antizapret"),
            ("openvpn_default", "openvpn_tcp", "openvpn_udp"),
            "Выберите хотя бы один вариант файла OpenVPN.",
        ),
        (
            has_wireguard,
            "WireGuard",
            ("wireguard_vpn", "wireguard_antizapret"),
            ("wireguard_wg", "wireguard_am"),
            "Выберите хотя бы одно приложение WireGuard.",
        ),
    )
    for available, family_name, profile_keys, variant_keys, variant_message in families:
        if not available:
            continue
        has_profile = any(protocols.get(key, False) for key in profile_keys)
        has_variant = any(protocols.get(key, False) for key in variant_keys)
        if has_profile and not has_variant:
            return variant_message
        if has_variant and not has_profile:
            return f"Выберите хотя бы один профиль {family_name}."
    return ""


def _subscription_protocols_enabled(protocols, has_openvpn, has_wireguard):
    openvpn_enabled = has_openvpn and (
        protocols.get("openvpn_vpn", False)
        or protocols.get("openvpn_antizapret", False)
    ) and (
        protocols.get("openvpn_default", False)
        or protocols.get("openvpn_tcp", False)
        or protocols.get("openvpn_udp", False)
    )
    wireguard_enabled = has_wireguard and (
        protocols.get("wireguard_vpn", False)
        or protocols.get("wireguard_antizapret", False)
    ) and (
        protocols.get("wireguard_wg", False)
        or protocols.get("wireguard_am", False)
    )
    return bool(openvpn_enabled or wireguard_enabled)


def _subscription_mode_enabled(raw_mode, protocols, has_openvpn, has_wireguard):
    return raw_mode != "disabled" and _subscription_protocols_enabled(
        protocols, has_openvpn, has_wireguard
    )


def _subscription_client_families(client_name):
    has_openvpn = (
        client_name in get_all_openvpn_clients()
        or bool(list_openvpn_ovpn_paths_for_client(client_name))
    )
    has_wireguard = bool(list_wg_conf_paths_for_client(client_name))
    return has_openvpn, has_wireguard


def _subscription_client_is_valid(client_name):
    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return False
    return any(_subscription_client_families(client_name))


@app.route("/api/openvpn/client-cert", methods=["POST"])
@login_required
def api_openvpn_client_cert():
    client_name = request.form.get("client_name", "").strip()
    days_raw = request.form.get("days", "").strip()

    if not days_raw.isdigit() or not (1 <= int(days_raw) <= 3650):
        return jsonify({"success": False, "message": "Укажите срок от 1 до 3650 дней."}), 400

    result = run_openvpn_add_or_renew_client(client_name, int(days_raw))
    if not result.get("success"):
        return jsonify(result), 400

    action = "client_cert_renew" if result.get("renewed") else "client_create"
    detail = f"{client_name} (до {result.get('cert_expiry_label', '—')})"
    if result.get("was_expired"):
        detail += ", истёкший сертификат"
    log_action(
        "web",
        getattr(current_user, "id", 0),
        getattr(current_user, "username", "admin"),
        action,
        detail,
    )
    return jsonify(result)


@app.route("/api/openvpn/client-block/schedule", methods=["POST"])
@login_required
def api_openvpn_client_block_schedule():
    client_name = request.form.get("client_name", "").strip()
    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    scheduled_at, error = _parse_scheduled_block_time(
        request.form.get("scheduled_at")
    )
    if error:
        return jsonify({"success": False, "message": error}), 400

    try:
        item = schedule_openvpn_block(
            client_name,
            scheduled_at,
            getattr(current_user, "username", "admin"),
        )
        log_action(
            "web",
            getattr(current_user, "id", 0),
            getattr(current_user, "username", "admin"),
            "user_ban_scheduled",
            f"{client_name}: {item['scheduled_at']}",
        )
        return jsonify(
            {
                "success": True,
                "client_name": client_name,
                "scheduled_at": item["scheduled_at"],
                "message": "Блокировка запланирована.",
            }
        )
    except (OSError, sqlite3.Error) as exc:
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/api/openvpn/client-block/schedule/cancel", methods=["POST"])
@login_required
def api_openvpn_client_block_schedule_cancel():
    client_name = request.form.get("client_name", "").strip()
    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    try:
        cancelled = cancel_scheduled_openvpn_block(client_name)
        if cancelled:
            log_action(
                "web",
                getattr(current_user, "id", 0),
                getattr(current_user, "username", "admin"),
                "user_ban_schedule_cancelled",
                client_name,
            )
        return jsonify(
            {
                "success": True,
                "client_name": client_name,
                "cancelled": cancelled,
                "message": (
                    "Отложенная блокировка отменена."
                    if cancelled
                    else "Отложенная блокировка не найдена."
                ),
            }
        )
    except (OSError, sqlite3.Error) as exc:
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/api/openvpn/client-block", methods=["POST"])
@login_required
def api_openvpn_client_block():
    client_name = request.form.get("client_name", "").strip()
    blocked_raw = request.form.get("blocked", "").strip().lower()

    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    should_block = blocked_raw in {"1", "true", "yes", "on"}

    try:
        ensure_client_connect_ban_check_block()
        banned_clients = read_banned_clients()

        if should_block:
            banned_clients.add(client_name)
        else:
            banned_clients.discard(client_name)

        write_banned_clients(banned_clients)
        cancel_scheduled_openvpn_block(client_name)
        return jsonify(
            {
                "success": True,
                "client_name": client_name,
                "blocked": should_block,
                "message": (
                    "Клиент заблокирован." if should_block else "Блокировка снята."
                ),
            }
        )
    except PermissionError:
        return (
            jsonify(
                {"success": False, "message": "Нет прав на запись banned_clients."}
            ),
            500,
        )
    except OSError as e:
        return (
            jsonify(
                {"success": False, "message": f"Ошибка работы с banned_clients: {e}"}
            ),
            500,
        )


@app.route("/api/openvpn/client-kick", methods=["POST"])
@login_required
def api_openvpn_client_kick():
    client_name = request.form.get("client_name", "").strip()
    protocol = request.form.get("protocol", "").strip() or None

    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    try:
        ensure_client_connect_ban_check_block()
        banned_clients = read_banned_clients()
        banned_clients.add(client_name)
        write_banned_clients(banned_clients)
        cancel_scheduled_openvpn_block(client_name)

        kicked, errors = kick_openvpn_client(client_name, protocol)

        if kicked:
            return jsonify(
                {
                    "success": True,
                    "client_name": client_name,
                    "kicked": True,
                    "blocked": True,
                    "message": "Клиент отключён и заблокирован.",
                }
            )
        return jsonify(
            {
                "success": True,
                "client_name": client_name,
                "kicked": False,
                "blocked": True,
                "message": "Клиент заблокирован. Отключение не удалось (возможно, уже оффлайн).",
                "errors": errors,
            }
        )

    except PermissionError:
        return (
            jsonify(
                {"success": False, "message": "Нет прав на запись banned_clients."}
            ),
            500,
        )
    except OSError as e:
        return jsonify({"success": False, "message": f"Ошибка: {e}"}), 500


@app.route("/api/openvpn/client-delete", methods=["POST"])
@login_required
def api_openvpn_client_delete():
    client_name = request.form.get("client_name", "").strip()
    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    if not os.path.isfile(CLIENT_SH_PATH):
        return jsonify({"success": False, "message": "Не найден скрипт client.sh"}), 500

    env = {
        **os.environ,
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    }
    try:
        proc = subprocess.run(
            [CLIENT_SH_PATH, "2", client_name],
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return (
            jsonify({"success": False, "message": "Превышено время ожидания client.sh"}),
            500,
        )
    except OSError as e:
        return jsonify({"success": False, "message": str(e)}), 500

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return (
            jsonify(
                {
                    "success": False,
                    "message": err or f"client.sh завершился с кодом {proc.returncode}",
                }
            ),
            500,
        )

    cancel_scheduled_openvpn_block(client_name)

    try:
        banned_clients = read_banned_clients()
        if client_name in banned_clients:
            banned_clients.discard(client_name)
            write_banned_clients(banned_clients)
    except OSError:
        pass

    try:
        revoke_client_subscription(client_name)
    except OSError:
        pass

    log_action(
        "web",
        getattr(current_user, "id", 0),
        getattr(current_user, "username", "admin"),
        "client_delete",
        f"{client_name} (OpenVPN)",
    )
    return jsonify(
        {
            "success": True,
            "client_name": client_name,
            "message": f"Клиент <b>{client_name}</b> удалён.",
        }
    )


@app.route("/api/openvpn/client-subscription-settings", methods=["GET", "POST"])
@login_required
def api_openvpn_client_subscription_settings():
    client_name = request.values.get("client_name", "").strip()
    if not _subscription_client_is_valid(client_name):
        return jsonify({"success": False, "message": "Клиент не найден."}), 404

    client_has_openvpn, client_has_wireguard = _subscription_client_families(client_name)
    has_openvpn, has_wireguard = client_has_openvpn, client_has_wireguard
    family = (request.values.get("family") or "").strip().lower()
    if family == "openvpn":
        has_wireguard = False
    elif family == "wireguard":
        has_openvpn = False
    if request.method == "GET":
        protocols = get_vpn_client_protocols(client_name)
        subscription_enabled = get_client_subscription_enabled(client_name)
        return jsonify({
            "success": True,
            "client_name": client_name,
            "temporary": get_client_subscription_temporary(client_name),
            "enabled": subscription_enabled,
            "lifetime_minutes": get_subscription_link_lifetime_minutes(),
            "url": get_client_subscription_url(client_name),
            "has_openvpn": has_openvpn,
            "has_wireguard": has_wireguard,
            "protocols": protocols,
            "service_warnings": (
                get_subscription_service_warnings(
                    protocols,
                    has_openvpn=has_openvpn,
                    has_wireguard=has_wireguard,
                )
                if subscription_enabled
                else []
            ),
        })

    raw_mode = (request.form.get("temporary") or "").strip().lower()
    if raw_mode not in ("true", "false", "disabled"):
        return jsonify({"success": False, "message": "Некорректный режим ссылки."}), 400

    protocols = get_vpn_client_protocols(client_name)
    for key in _SUBSCRIPTION_PROTOCOL_KEYS:
        applies = ((key.startswith("openvpn_") and has_openvpn)
                   or (key.startswith("wireguard_") and has_wireguard))
        if not applies:
            continue
        raw_value = (request.form.get(key) or "false").strip().lower()
        if raw_value not in ("true", "false"):
            return jsonify({"success": False, "message": "Некорректные настройки."}), 400
        protocols[key] = raw_value == "true"

    selection_error = _subscription_protocol_selection_error(
        protocols, has_openvpn, has_wireguard
    )
    if selection_error:
        return jsonify({"success": False, "message": selection_error}), 400

    try:
        set_vpn_client_protocols(client_name, protocols)
        temporary = get_client_subscription_temporary(client_name)
        if raw_mode != "disabled":
            temporary = set_client_subscription_temporary(
                client_name, raw_mode == "true"
            )
        enabled = set_client_subscription_enabled(
            client_name,
            _subscription_mode_enabled(
                raw_mode, protocols, client_has_openvpn, client_has_wireguard
            ),
        )
    except OSError as exc:
        return jsonify({"success": False, "message": str(exc)}), 500

    log_action(
        "web",
        getattr(current_user, "id", 0),
        getattr(current_user, "username", "admin"),
        "client_protocols_change",
        f"Публичная ссылка VPN-клиента {client_name}",
    )
    return jsonify({
        "success": True,
        "client_name": client_name,
        "temporary": temporary,
        "enabled": enabled,
        "url": get_client_subscription_url(client_name),
        "service_warnings": (
            get_subscription_service_warnings(
                protocols,
                has_openvpn=has_openvpn,
                has_wireguard=has_wireguard,
            )
            if enabled
            else []
        ),
    })


@app.route("/api/openvpn/client-subscription-revoke", methods=["POST"])
@login_required
def api_openvpn_client_subscription_revoke():
    client_name = request.form.get("client_name", "").strip()
    if not _subscription_client_is_valid(client_name):
        return jsonify({"success": False, "message": "Клиент не найден."}), 404
    try:
        revoked = revoke_client_subscription(client_name, preserve_preference=True)
    except OSError as exc:
        return jsonify({"success": False, "message": str(exc)}), 500
    log_action(
        "web",
        getattr(current_user, "id", 0),
        getattr(current_user, "username", "admin"),
        "client_subscription_revoke",
        f"VPN-клиент {client_name}: ссылок отозвано {revoked}",
    )
    return jsonify({
        "success": True,
        "client_name": client_name,
        "message": "Ссылки клиента отозваны.",
    })


@app.route("/api/openvpn/client-subscription", methods=["POST"])
@login_required
def api_openvpn_client_subscription():
    client_name = request.form.get("client_name", "").strip()
    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    if (
        client_name not in get_all_openvpn_clients()
        and not list_openvpn_ovpn_paths_for_client(client_name)
        and not list_wg_conf_paths_for_client(client_name)
    ):
        return jsonify({"success": False, "message": "Клиент не найден."}), 404

    if not are_subscriptions_active():
        return (
            jsonify(
                {
                    "success": False,
                    "message": subscriptions_unavailable_message(),
                }
            ),
            503,
        )

    if not get_client_subscription_enabled(client_name):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Выдача ссылки для клиента отключена.",
                }
            ),
            409,
        )

    raw = (request.form.get("temporary") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        try:
            set_client_subscription_temporary(client_name, True)
        except OSError as e:
            return jsonify({"success": False, "message": str(e)}), 500
    elif raw in ("0", "false", "no", "off"):
        try:
            set_client_subscription_temporary(client_name, False)
        except OSError as e:
            return jsonify({"success": False, "message": str(e)}), 500

    rotate = (request.form.get("rotate") or "").strip().lower() in (
        "1", "true", "yes", "on"
    )
    try:
        if rotate:
            revoke_client_subscription(client_name, preserve_preference=True)
        url = create_subscription_url(client_name)
    except OSError as e:
        return jsonify({"success": False, "message": str(e)}), 500

    if not url:
        return jsonify({"success": False, "message": "Не удалось создать ссылку."}), 500

    if rotate:
        log_action(
            "web",
            getattr(current_user, "id", 0),
            getattr(current_user, "username", "admin"),
            "client_subscription_rotate",
            f"VPN-клиент {client_name}",
        )

    return jsonify(
        {
            "success": True,
            "client_name": client_name,
            "url": url,
            "temporary": get_client_subscription_temporary(client_name),
        }
    )


@app.route("/api/openvpn/client-subscription-mode", methods=["POST"])
@login_required
def api_openvpn_client_subscription_mode():
    client_name = request.form.get("client_name", "").strip()
    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    if (
        client_name not in get_all_openvpn_clients()
        and not list_openvpn_ovpn_paths_for_client(client_name)
        and not list_wg_conf_paths_for_client(client_name)
    ):
        return jsonify({"success": False, "message": "Клиент не найден."}), 404

    raw = (request.form.get("temporary") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        temporary = True
    elif raw in ("0", "false", "no", "off"):
        temporary = False
    else:
        return jsonify({"success": False, "message": "Некорректный режим ссылки."}), 400

    try:
        saved = set_client_subscription_temporary(client_name, temporary)
    except OSError as e:
        return jsonify({"success": False, "message": str(e)}), 500

    if saved is None:
        return jsonify({"success": False, "message": "Не удалось сохранить режим ссылки."}), 500

    return jsonify(
        {
            "success": True,
            "client_name": client_name,
            "temporary": saved,
        }
    )


@app.route("/api/openvpn/client-config", methods=["GET"])
@login_required
def api_openvpn_client_config():
    """Список профилей .ovpn или содержимое по index."""
    client_name = request.args.get("client_name", "").strip()
    idx_raw = request.args.get("index", "").strip()

    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    paths = list_openvpn_ovpn_paths_for_client(client_name)
    if idx_raw == "":
        items = [
            {"index": i, "label": ovpn_profile_label(p)} for i, p in enumerate(paths)
        ]
        return jsonify({"success": True, "items": items})

    try:
        idx = int(idx_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Некорректный index."}), 400

    if idx < 0 or idx >= len(paths):
        return jsonify({"success": False, "message": "Профиль не найден."}), 404

    path = paths[idx]
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        return jsonify({"success": False, "message": str(e)}), 500

    return jsonify(
        {
            "success": True,
            "config_text": text,
            "label": ovpn_profile_label(path),
            "filename": os.path.basename(path),
        }
    )


@app.route("/api/openvpn/client-config/download", methods=["GET"])
@login_required
def api_openvpn_client_config_download():
    """Скачивание .ovpn по имени клиента и индексу профиля."""
    client_name = request.args.get("client_name", "").strip()
    idx_raw = request.args.get("index", "0").strip()

    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    try:
        idx = int(idx_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Некорректный index."}), 400

    paths = list_openvpn_ovpn_paths_for_client(client_name)
    if idx < 0 or idx >= len(paths):
        return jsonify({"success": False, "message": "Профиль не найден."}), 404

    path = paths[idx]
    if not os.path.isfile(path):
        return jsonify({"success": False, "message": "Файл не найден."}), 404

    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path),
        mimetype="application/x-openvpn-profile",
    )


@app.route("/api/wireguard/client-config", methods=["GET"])
@login_required
def api_wireguard_client_config():
    """Список .conf профилей или содержимое по index."""
    client_name = request.args.get("client_name", "").strip()
    idx_raw = request.args.get("index", "").strip()

    if not wg_client_name_param_ok(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    paths = list_wg_conf_paths_for_client(client_name)
    shorten = bool(read_settings().get("shorten_wg_filenames", False))
    if idx_raw == "":
        items = [
            {
                "index": i,
                "label": wg_conf_profile_label(p),
                "filename": wg_conf_short_filename(p) if shorten else os.path.basename(p),
            }
            for i, p in enumerate(paths)
        ]
        return jsonify({"success": True, "items": items})

    try:
        idx = int(idx_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Некорректный index."}), 400

    if idx < 0 or idx >= len(paths):
        return jsonify({"success": False, "message": "Профиль не найден."}), 404

    path = paths[idx]
    if not wg_conf_path_is_allowed(path):
        return jsonify({"success": False, "message": "Недопустимый путь."}), 403

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        return jsonify({"success": False, "message": str(e)}), 500

    return jsonify(
        {
            "success": True,
            "config_text": text,
            "label": wg_conf_profile_label(path),
            "filename": wg_conf_short_filename(path) if shorten else os.path.basename(path),
        }
    )


@app.route("/api/wireguard/client-config/download", methods=["GET"])
@login_required
def api_wireguard_client_config_download():
    """Скачивание .conf по имени клиента и индексу профиля."""
    client_name = request.args.get("client_name", "").strip()
    idx_raw = request.args.get("index", "0").strip()

    if not wg_client_name_param_ok(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    try:
        idx = int(idx_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Некорректный index."}), 400

    paths = list_wg_conf_paths_for_client(client_name)
    if idx < 0 or idx >= len(paths):
        return jsonify({"success": False, "message": "Профиль не найден."}), 404

    path = paths[idx]
    if not wg_conf_path_is_allowed(path):
        return jsonify({"success": False, "message": "Недопустимый путь."}), 403

    if not os.path.isfile(path):
        return jsonify({"success": False, "message": "Файл не найден."}), 404

    shorten = bool(read_settings().get("shorten_wg_filenames", False))
    download_name = wg_conf_short_filename(path) if shorten else os.path.basename(path)

    return send_file(
        path,
        as_attachment=True,
        download_name=download_name,
        mimetype="text/plain",
    )


@app.route("/api/wireguard/client-config/qr", methods=["GET"])
@login_required
def api_wireguard_client_config_qr():
    """PNG QR-код конфигурации WireGuard (qrencode)."""
    client_name = request.args.get("client_name", "").strip()
    idx_raw = request.args.get("index", "0").strip()

    if not wg_client_name_param_ok(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    try:
        idx = int(idx_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Некорректный index."}), 400

    paths = list_wg_conf_paths_for_client(client_name)
    if idx < 0 or idx >= len(paths):
        return jsonify({"success": False, "message": "Профиль не найден."}), 404

    path = paths[idx]
    if not wg_conf_path_is_allowed(path):
        return jsonify({"success": False, "message": "Недопустимый путь."}), 403

    if not os.path.isfile(path):
        return jsonify({"success": False, "message": "Файл не найден."}), 404

    try:
        png_data = wg_qr_png_for_conf_path(path)
    except FileNotFoundError as e:
        return jsonify({"success": False, "message": str(e)}), 503
    except OSError as e:
        return jsonify({"success": False, "message": str(e)}), 500
    except RuntimeError as e:
        return jsonify({"success": False, "message": str(e)}), 500

    return send_file(
        io.BytesIO(png_data),
        mimetype="image/png",
        download_name="wireguard-qr.png",
    )
