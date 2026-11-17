import json
import os
import subprocess
import urllib.error
import urllib.request

from src.ui.constants import BOT_SERVICE_NAME
from src.ui.state import BOT_RESTART_LOCK


def get_telegram_bot_identity(bot_token, timeout=3):
    """Return the bot display name and public Telegram link for a valid token."""
    token = (bot_token or "").strip()
    if not token:
        return None

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/getMe",
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return None

    if not payload.get("ok"):
        return None

    result = payload.get("result") or {}
    username = (result.get("username") or "").strip()
    if not username:
        return None

    name = " ".join(
        part.strip()
        for part in (result.get("first_name") or "", result.get("last_name") or "")
        if part and part.strip()
    )
    return {
        "name": name or f"@{username}",
        "username": username,
        "url": f"https://t.me/{username}",
    }


def restart_telegram_bot():
    with BOT_RESTART_LOCK:
        if not os.path.exists("/etc/systemd/system/telegram-bot.service"):
            return False, (
                "Служба telegram-bot не создана. Выполните команду "
                "sudo bash /root/web/scripts/update.sh и ответьте Y на вопрос "
                "об установке Telegram-бота."
            )
        try:
            subprocess.run(
                ["/bin/systemctl", "restart", BOT_SERVICE_NAME],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return True, None
        except subprocess.CalledProcessError as exc:
            try:
                subprocess.run(
                    ["/bin/systemctl", "reset-failed", f"{BOT_SERVICE_NAME}.service"],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except Exception:
                pass
            return False, exc.stderr.strip() or "неизвестная ошибка"


def stop_telegram_bot():
    with BOT_RESTART_LOCK:
        if not os.path.exists("/etc/systemd/system/telegram-bot.service"):
            return False, "Служба telegram-bot не создана"
        try:
            subprocess.run(
                ["/bin/systemctl", "stop", BOT_SERVICE_NAME],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return True, None
        except subprocess.CalledProcessError as exc:
            return False, exc.stderr.strip() or "неизвестная ошибка"


def get_telegram_bot_status():
    try:
        result = subprocess.run(
            ["/bin/systemctl", "is-active", BOT_SERVICE_NAME],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        status = result.stdout.strip()
        return status == "active"
    except Exception:
        return False
