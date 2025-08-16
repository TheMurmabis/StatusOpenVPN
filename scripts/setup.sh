#!/bin/bash

# Обработка ошибок
set -e

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RESET='\e[0m'

# Переменные
TARGET_DIR="/root/web"
DEFAULT_PORT=1234
ENV_FILE="$TARGET_DIR/src/.env"
SERVICE_FILE="/etc/systemd/system/StatusOpenVPN.service"
SETUP_FILE="$TARGET_DIR/setup"
SSL_SCRIPT="$TARGET_DIR/scripts/ssl.sh"
SERVER_URL=""

# Проверка версии Python и установка venv
install_python_venv() {
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo "Detected Python version: $PYTHON_VERSION"

    if ! dpkg -s "python${PYTHON_VERSION}-venv" >/dev/null 2>&1; then
        echo "Installing python${PYTHON_VERSION}-venv..."
        apt update && apt install -y "python${PYTHON_VERSION}-venv" || { echo -e "${RED}❌ Failed to install python${PYTHON_VERSION}-venv${RESET}"; exit 1; }
    else
        echo "python${PYTHON_VERSION}-venv is already installed."
    fi
}

# Проверка порта
check_port_free() {
    local PORT=$1
    if ! ss -tuln | grep -q ":$PORT "; then
        return 0
    else
        return 1
    fi
}

# === Запрос порта ===
read -e -p "Would you like to change the default port $DEFAULT_PORT? (Y/N): " -i N CHANGE_PORT
if [[ "$CHANGE_PORT" =~ ^[Yy]$ ]]; then
    while true; do
        read -p "Please enter a new port number: " NEW_PORT
        if [[ "$NEW_PORT" =~ ^[0-9]+$ ]] && [ "$NEW_PORT" -ge 1 ] && [ "$NEW_PORT" -le 65535 ]; then
            if check_port_free "$NEW_PORT"; then
                PORT=$NEW_PORT
                echo "Port $PORT is free and will be used."
                break
            else
                echo "Port $NEW_PORT is already in use. Please try another one."
            fi
        else
            echo "Invalid port number. Please enter a number between 1 and 65535."
        fi
    done
else
    PORT=$DEFAULT_PORT
    echo "Using default port $PORT."
fi

# === Клонирование проекта ===
echo "Cloning repository into $TARGET_DIR..."
git clone https://github.com/TheMurmabis/StatusOpenVPN.git $TARGET_DIR
cd $TARGET_DIR

# === Python окружение ===
install_python_venv
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

if [ -f "requirements.txt" ]; then
    echo "Installing requirements..."
    pip install -r requirements.txt
fi

# Создание и настройка systemd-сервиса
SERVICE_FILE="/etc/systemd/system/StatusOpenVPN.service"
echo "Creating systemd service file at $SERVICE_FILE..."
cat <<EOF | sudo tee $SERVICE_FILE
[Unit]
Description=Gunicorn instance to serve StatusOpenVPN
After=network.target

[Service]
User=root
Group=www-data
WorkingDirectory=$TARGET_DIR
Environment="PATH=$TARGET_DIR/venv/bin"
ExecStart=$TARGET_DIR/venv/bin/gunicorn -w 4 main:app -b 0.0.0.0:$PORT

[Install]
WantedBy=multi-user.target
EOF

# Создание logs.service
LOGS_SERVICE="/etc/systemd/system/logs.service"
cat <<EOF | sudo tee $LOGS_SERVICE
[Unit]
Description=Run logs.py script

[Service]
Type=oneshot
ExecStart=$TARGET_DIR/venv/bin/python $TARGET_DIR/src/logs.py
EOF

LOGS_TIMER="/etc/systemd/system/logs.timer"
cat <<EOF | sudo tee $LOGS_TIMER
[Unit]
Description=Run logs.py every 30 seconds

[Timer]
OnBootSec=30s
OnUnitActiveSec=30s
Unit=logs.service

[Install]
WantedBy=timers.target
EOF

# Создание wg_stats.service
WG_STATS="/etc/systemd/system/wg_stats.service"
cat <<EOF | sudo tee $WG_STATS
[Unit]
Description=WireGuard Traffic Statistics Collector
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$TARGET_DIR/src
Environment="PATH=$TARGET_DIR/venv/bin"
ExecStart=$TARGET_DIR/venv/bin/python $TARGET_DIR/src/wg_stats.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# === Telegram Bot (с сохранением состояния) ===
BOT_ENABLED=0
if [[ -f "$SETUP_FILE" ]]; then
    source "$SETUP_FILE"
fi

if [[ "$BOT_ENABLED" -ne 1 ]]; then
    read -e -p "Would you like to install the Telegram bot service? (Y/N): " -i Y INSTALL_BOT
    if [[ "$INSTALL_BOT" =~ ^[Yy]$ ]]; then
        BOT_SERVICE="/etc/systemd/system/telegram-bot.service"
        echo "Creating Telegram bot service..."

        cat <<EOF | sudo tee $BOT_SERVICE
[Unit]
Description=Telegram Bot Service
After=network.target
StartLimitBurst=3
StartLimitIntervalSec=300

[Service]
User=root
Group=www-data
WorkingDirectory=$TARGET_DIR
Environment="PATH=$TARGET_DIR/venv/bin"
ExecStart=$TARGET_DIR/venv/bin/python $TARGET_DIR/src/vpn_bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

        if [ ! -f "$ENV_FILE" ]; then
            echo "Creating .env file..."
            cat <<EOF > $ENV_FILE
BOT_TOKEN=<Enter API Token>
ADMIN_ID=<Enter your user ID>
EOF
            echo -e "${YELLOW}⚠️  Warning: The .env file has been created, but BOT_TOKEN is empty.${RESET}"
        fi

        BOT_ENABLED=1
    else
        BOT_ENABLED=0
    fi
fi

# Перезагрузка systemd и запуск сервиса
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload
sudo systemctl enable StatusOpenVPN wg_stats logs.timer
sudo systemctl start StatusOpenVPN wg_stats logs.timer

if [[ "$BOT_ENABLED" -eq 1 ]]; then
    sudo systemctl enable telegram-bot
fi

# === Первичная настройка ===
EXTERNAL_IP=$(curl -4 -s ifconfig.me)
echo "Running initial admin setup..."
ADMIN_PASS=$(PYTHONIOENCODING=utf-8 python3 -c "from main import add_admin; print(add_admin())")

# Вывод информации о доступности сервера
echo "--------------------------------------------"
echo -e "${GREEN}✅ Setup completed successfully${RESET}"
echo "--------------------------------------------"
echo -e "Server is available at: \e[4;38;5;33mhttp://$EXTERNAL_IP:$PORT\e[0m"
echo -e "Admin login: ${GREEN}admin${RESET}"
echo -e "Admin password: ${GREEN}$ADMIN_PASS${RESET}"
echo "--------------------------------------------"

# Удаление скрипта установки
rm -f $TARGET_DIR/scripts/setup.sh
