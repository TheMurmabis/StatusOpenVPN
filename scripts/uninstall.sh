#!/bin/bash

GREEN="\e[32m"
RED="\e[31m"
YELLOW="\e[33m"
RESET="\e[0m"

# Функции для вывода статуса
success_status() {
  echo -e "${GREEN}✔ $1${RESET}"
}

error_status() {
  echo -e "${RED}❌ $1${RESET}"
}

info_status() {
  echo -e "${YELLOW}ℹ $1${RESET}"
}

# === Подгрузка setup файла ===
SETUP_FILE="/root/web/setup.env"
if [[ -f "$SETUP_FILE" ]]; then
    source "$SETUP_FILE"
fi

# === Удаление SSL, если есть домен ===
if [[ -n "$DOMAIN" && -f "/root/web/ssl.sh" ]]; then
    info_status "Removing SSL for domain: $DOMAIN"
    bash /root/web/ssl.sh -r "$DOMAIN"
fi

# === Остановка и отключение сервисов ===
info_status "Stopping and disabling the service"
if sudo systemctl stop StatusOpenVPN && sudo systemctl disable StatusOpenVPN; then
    success_status "Service stopped and disabled successfully"
else
    error_status "Failed to stop and disable the service"
fi

info_status "Stopping and disabling logs.service and logs.timer"
sudo systemctl stop logs.service logs.timer
sudo systemctl disable logs.service logs.timer

# === Удаление systemd unit файлов ===
SYSTEMD_UNITS=(
    "StatusOpenVPN.service"
    "telegram-bot.service"
    "logs.service"
    "logs.timer"
    "wg_stats.service"
)

for unit in "${SYSTEMD_UNITS[@]}"; do
    if sudo rm -f "/etc/systemd/system/$unit"; then
        success_status "$unit deleted successfully"
    else
        error_status "Failed to delete $unit"
    fi
done

# === Перезапуск systemd ===
info_status "Reloading systemd"
if sudo systemctl daemon-reload; then
    success_status "Systemd reloaded successfully"
else
    error_status "Failed to reload systemd"
fi

# === Удаление директории с проектом ===
info_status "Deleting project directory /root/web"
if sudo rm -rf /root/web; then
    success_status "Directory deleted successfully"
else
    error_status "Failed to delete the directory"
fi
