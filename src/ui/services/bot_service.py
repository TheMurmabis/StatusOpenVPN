import os
import subprocess

from src.ui.constants import BOT_SERVICE_NAME
from src.ui.state import BOT_RESTART_LOCK


def restart_telegram_bot():
    with BOT_RESTART_LOCK:
        if not os.path.exists("/etc/systemd/system/telegram-bot.service"):
            return False, "Служба telegram-bot не создана"
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
