#!/bin/bash

GREEN="\e[32m"
RED="\e[31m"
YELLOW="\e[33m"
RESET="\e[0m"

TARGET_DIR="/root/web"
BACKUP_DIR="/opt/StatusOpenVPN/backup"
DATABASES_DIR="$TARGET_DIR/src/databases"
DB_BACKUP_DIR="$BACKUP_DIR/src/databases"
SETTINGS_FILE="$TARGET_DIR/src/settings.json"
SETTINGS_BACKUP_FILE="$BACKUP_DIR/src/settings.json"

run_as_root() {
  if [[ "$EUID" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    echo "Error: sudo is not installed. Run this script as root." >&2
    exit 1
  fi
}

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

has_database_files() {
  if [[ -d "$DATABASES_DIR" ]] && compgen -G "$DATABASES_DIR/*.db" > /dev/null; then
    return 0
  fi
  if compgen -G "$TARGET_DIR/src/*.db" > /dev/null; then
    return 0
  fi
  return 1
}

has_backup_files() {
  if has_database_files; then
    return 0
  fi
  [[ -f "$SETTINGS_FILE" ]]
}

backup_user_data() {
  local copied=0

  if has_database_files; then
    if ! mkdir -p "$DB_BACKUP_DIR"; then
      return 1
    fi

    if [[ -d "$DATABASES_DIR" ]]; then
      for db in "$DATABASES_DIR"/*.db; do
        [[ -f "$db" ]] || continue
        if cp -a "$db" "$DB_BACKUP_DIR"/; then
          copied=$((copied + 1))
        else
          return 1
        fi
      done
    fi

    for db in "$TARGET_DIR/src"/*.db; do
      [[ -f "$db" ]] || continue
      if cp -a "$db" "$DB_BACKUP_DIR"/; then
        copied=$((copied + 1))
      else
        return 1
      fi
    done
  fi

  if [[ -f "$SETTINGS_FILE" ]]; then
    if ! mkdir -p "$(dirname "$SETTINGS_BACKUP_FILE")"; then
      return 1
    fi
    if cp -a "$SETTINGS_FILE" "$SETTINGS_BACKUP_FILE"; then
      copied=$((copied + 1))
    else
      return 1
    fi
  fi

  [[ "$copied" -gt 0 ]]
}

offer_user_data_backup() {
  if ! has_backup_files; then
    info_status "No database files or settings.json found, skipping backup"
    return
  fi

  read -e -p "Save backups (databases and settings.json) to $BACKUP_DIR? (Y/N): " -i Y SAVE_BACKUP
  if [[ "$SAVE_BACKUP" =~ ^[Yy]$ ]]; then
    if backup_user_data; then
      success_status "Backups saved to $BACKUP_DIR"
    else
      error_status "Failed to save backups"
    fi
  else
    info_status "Backup skipped"
  fi
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
if run_as_root systemctl stop StatusOpenVPN && run_as_root systemctl disable StatusOpenVPN; then
    success_status "Service stopped and disabled successfully"
else
    error_status "Failed to stop and disable the service"
fi

info_status "Stopping and disabling logs.service and logs.timer"
run_as_root systemctl stop logs.service logs.timer
run_as_root systemctl disable logs.service logs.timer

# === Удаление systemd unit файлов ===
SYSTEMD_UNITS=(
    "StatusOpenVPN.service"
    "telegram-bot.service"
    "logs.service"
    "logs.timer"
    "wg_stats.service"
)

for unit in "${SYSTEMD_UNITS[@]}"; do
    if run_as_root rm -f "/etc/systemd/system/$unit"; then
        success_status "$unit deleted successfully"
    else
        error_status "Failed to delete $unit"
    fi
done

# === Перезапуск systemd ===
info_status "Reloading systemd"
if run_as_root systemctl daemon-reload; then
    success_status "Systemd reloaded successfully"
else
    error_status "Failed to reload systemd"
fi

# === Резервное копирование баз данных и settings.json ===
offer_user_data_backup

# === Удаление директории с проектом ===
info_status "Deleting project directory $TARGET_DIR"
if run_as_root rm -rf "$TARGET_DIR"; then
    success_status "Directory deleted successfully"
else
    error_status "Failed to delete the directory"
fi
