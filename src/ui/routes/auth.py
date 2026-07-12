import time
import json
import urllib.request

from flask import (
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from src.forms import LoginForm
from src.tg_bot.audit import log_action
from src.ui.extensions import app, bcrypt
from src.ui.services.admins_service import parse_admin_ids
from src.ui.services.auth_service import User, get_db_connection
from src.ui.services.bot_service import get_telegram_bot_status
from src.ui.services.env_service import read_env_values
from src.ui.services.settings_service import read_settings


def _send_failed_login_bot_alert(username: str, client_ip: str, failed_attempts: int):
    settings_data = read_settings()
    bot_enabled = bool(settings_data.get("bot_enabled", False)) or get_telegram_bot_status()
    if not bot_enabled:
        return

    env_values = read_env_values()
    bot_token = (env_values.get("BOT_TOKEN") or "").strip()
    admin_ids = parse_admin_ids(env_values.get("ADMIN_ID", ""))
    if not bot_token or not admin_ids:
        return

    display_username = username.strip() or "не указан"
    display_ip = client_ip or "не определен"
    text = (
        "⚠️ Неудачные попытки входа в веб-панель\n"
        f"Логин: {display_username}\n"
        f"IP: {display_ip}\n"
        f"Попыток подряд: {failed_attempts}"
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for admin_id in admin_ids:
        if not str(admin_id).isdigit():
            continue
        payload = {"chat_id": int(admin_id), "text": text}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=3):
                pass
        except Exception:
            continue


@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    session.pop("last_activity", None)
    return redirect(url_for("login"))


@app.before_request
def track_last_activity():
    if request.path.startswith("/api/"):
        return

    session.permanent = True
    session["last_activity"] = time.time()


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    form = LoginForm()
    error_message = None

    if form.validate_on_submit():
        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (form.username.data,)
        ).fetchone()
        conn.close()

        if user and bcrypt.check_password_hash(user["password"], form.password.data):
            session["failed_login_attempts"] = 0
            user_obj = User(
                user_id=user["id"],
                username=user["username"],
                role=user["role"],
                password=user["password"],
            )
            login_user(user_obj, remember=form.remember_me.data)

            session.permanent = form.remember_me.data

            client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
            if client_ip and "," in client_ip:
                client_ip = client_ip.split(",")[0].strip()
            log_action(
                "web",
                user["username"],
                user["username"],
                "web_login",
                "",
                client_ip or "",
            )

            next_page = request.args.get("next")
            return redirect(next_page or url_for("home"))
        else:
            failed_attempts = int(session.get("failed_login_attempts", 0)) + 1
            session["failed_login_attempts"] = failed_attempts
            if failed_attempts == 3:
                client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
                if client_ip and "," in client_ip:
                    client_ip = client_ip.split(",")[0].strip()
                _send_failed_login_bot_alert(
                    username=form.username.data or "",
                    client_ip=client_ip or "",
                    failed_attempts=failed_attempts,
                )
            error_message = "Неправильный логин или пароль!"

    resp = make_response(
        render_template("login.html", form=form, error_message=error_message)
    )
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp
