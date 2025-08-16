#!/bin/bash 

# Обработка ошибок
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RESET='\e[0m'

# Переменные
TARGET_DIR="/root/web"
SETUP_FILE="$TARGET_DIR/setup"
DEFAULT_PORT=1234
ENV_FILE="$TARGET_DIR/src/.env"
SSL_SCRIPT="$TARGET_DIR/scripts/ssl.sh"
SERVICE_FILE="/etc/systemd/system/StatusOpenVPN.service"
SERVER_URL=""

# === Получение текущего порта ===
if [ -f "$SERVICE_FILE" ]; then
    CURRENT_PORT=$(grep -oP '(?<=-b 0.0.0.0:)[0-9]+' "$SERVICE_FILE" || echo "$DEFAULT_PORT")
else
    CURRENT_PORT=$DEFAULT_PORT
fi

# === Проверка порта ===
check_port_free() {
    local PORT=$1
    if ! ss -tuln | grep -q ":$PORT "; then
        return 0
    else
        return 1
    fi
}

# === Сохранение переменных ===
save_setup_var() {
    local key=$1
    local value=$2
    if grep -q "^$key=" "$SETUP_FILE" 2>/dev/null; then
        sed -i "s|^$key=.*|$key=$value|" "$SETUP_FILE"
    else
        echo "$key=$value" >> "$SETUP_FILE"
    fi
}

# === Ввод нового порта ===
read -e -p "Would you like to change the current port $CURRENT_PORT? (Y/N): " -i N CHANGE_PORT
if [[ "$CHANGE_PORT" =~ ^[Yy]$ ]]; then
    sudo systemctl stop StatusOpenVPN
    while true; do
        read -p "Please enter a new port number: " NEW_PORT
        if [[ "$NEW_PORT" =~ ^[0-9]+$ ]] && [ "$NEW_PORT" -ge 1 ] && [ "$NEW_PORT" -le 65535 ]; then
            if check_port_free "$NEW_PORT"; then
                PORT=$NEW_PORT
                echo "Port $PORT is free and will be used."
                break
            else
                echo "Port $NEW_PORT is already in use."
            fi
        else
            echo "Invalid port."
        fi
    done
else
    PORT=$CURRENT_PORT
fi

# === Обновление репозитория ===
cd $TARGET_DIR
git reset --hard
git fetch origin && git reset --hard origin/main

# Активация виртуального окружения
source venv/bin/activate
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

# === Обновление systemd сервиса ===
if [ -f "$SERVICE_FILE" ]; then
    sudo sed -i "s/-b 0.0.0.0:[0-9]*/-b 0.0.0.0:$PORT/" $SERVICE_FILE
else
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
fi

# === Логика HTTPS ===
get_server_ip() { curl -s http://checkip.amazonaws.com; }

check_domain_ip() {
    local domain="$1"
    local server_ip
    server_ip=$(get_server_ip)
    local domain_ip
    domain_ip=$(getent ahostsv4 "$domain" | awk '{print $1}' | head -n1)
    [[ "$server_ip" == "$domain_ip" ]]
}

if [[ -f "$SETUP_FILE" ]]; then
    source "$SETUP_FILE"
fi

# Сначала спрашиваем, хотим ли включить HTTPS
if [[ "$HTTPS_ENABLED" -ne 1 ]]; then
    read -p "Do you want to enable HTTPS? (y/N): " enable_ssl
    if [[ "$enable_ssl" =~ ^[Yy]$ ]]; then
        HTTPS_ENABLED=1
        save_setup_var "HTTPS_ENABLED" "1"
    else
        HTTPS_ENABLED=0
        save_setup_var "HTTPS_ENABLED" "0"
    fi
fi

# Если HTTPS выбран, запрашиваем домен и проверяем его
if [[ "$HTTPS_ENABLED" -eq 1 ]]; then
    while true; do
        if [[ -z "$DOMAIN" ]]; then
            read -e -p "Enter your domain (example.com): " DOMAIN
        fi
        if check_domain_ip "$DOMAIN"; then
            save_setup_var "DOMAIN" "$DOMAIN"
            break
        else
            echo -e "${RED}Domain does not point to this server. Try again.${RESET}"
            DOMAIN=""
        fi
    done

    CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
    NGINX_CONF="/etc/nginx/sites-enabled/$DOMAIN"

    if [[ -f "$CERT_PATH" ]] && openssl x509 -checkend 86400 -noout -in "$CERT_PATH" >/dev/null 2>&1 \
       && [[ -f "$NGINX_CONF" ]] && grep -q "# Created by StatusOpenVPN" "$NGINX_CONF"; then
        echo -e "${YELLOW}HTTPS already enabled and valid for: $DOMAIN${RESET}"
        SERVER_URL="https://$DOMAIN"
    else
        if [[ -f "$SSL_SCRIPT" ]]; then
            if bash "$SSL_SCRIPT" -i "$DOMAIN"; then
                echo -e "${GREEN}HTTPS successfully enabled for: $DOMAIN${RESET}"
                SERVER_URL="https://$DOMAIN"
            else
                echo -e "${RED}SSL setup failed.${RESET}"
                HTTPS_ENABLED=0
                save_setup_var "HTTPS_ENABLED" "0"
            fi
        else
            echo -e "${RED}SSL script not found.${RESET}"
            HTTPS_ENABLED=0
            save_setup_var "HTTPS_ENABLED" "0"
        fi
    fi
fi

if [[ -z "$SERVER_URL" ]]; then
    SERVER_URL="http://$EXTERNAL_IP:$PORT"
fi

# === Telegram Bot (состояние сохраняется) ===
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
            echo -e "${YELLOW}Warning: The .env file has been created, but BOT_TOKEN is empty.${RESET}"
        fi

        save_setup_var "BOT_ENABLED" "1"
        sudo systemctl enable telegram-bot
    else
        save_setup_var "BOT_ENABLED" "0"
    fi
else
    echo -e "${GREEN}Telegram bot already enabled.${RESET}"
fi

# === Перезагрузка сервисов ===
sudo systemctl daemon-reload
sudo systemctl restart StatusOpenVPN
sudo systemctl enable wg_stats
sudo systemctl restart wg_stats
sudo systemctl enable --now logs.timer
sudo systemctl restart logs.timer logs.service

EXTERNAL_IP=$(curl -4 -s ifconfig.me)

echo "--------------------------------------------"
echo -e "Server is available at: \e[4;38;5;33m$SERVER_URL\e[0m"
echo "--------------------------------------------"

rm -f $TARGET_DIR/scripts/setup.sh
