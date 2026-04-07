#!/bin/bash 

# Обработка ошибок
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RESET='\e[0m'

# Переменные
TARGET_DIR="/root/web"
SRC="$TARGET_DIR/src"
DST="$TARGET_DIR/src/databases"
SETUP_FILE="$TARGET_DIR/setup"
DEFAULT_PORT=1234
ENV_FILE="$TARGET_DIR/src/.env"
SSL_SCRIPT="$TARGET_DIR/scripts/ssl.sh"
SERVICE_FILE="/etc/systemd/system/StatusOpenVPN.service"
LOGS_SERVICE="/etc/systemd/system/logs.service"
SERVER_URL=""
INTERFACES=("antizapret-tcp" "vpn-tcp" "antizapret-udp" "vpn-udp" "vpn" "antizapret")

# Для обхода проблемы с vnStat
OVERRIDE_DIR="/etc/systemd/system/vnstat.service.d"
OVERRIDE_FILE="$OVERRIDE_DIR/override.conf"
SLEEP_LINE="ExecStartPre=/bin/sleep 10"
changes_made=false # Для отслеживания изменений

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
    pip install -q -r requirements.txt > /dev/null
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

# Проверяем, есть ли SECRET_KEY
if ! grep -q 'SECRET_KEY=' "$SERVICE_FILE"; then
    SECRET_KEY=$(openssl rand -hex 32)

    sudo sed -i "/^Environment=\"PATH=/a Environment=\"SECRET_KEY=$SECRET_KEY\"" "$SERVICE_FILE"

    # Перечитываем systemd и перезапускаем сервис
    sudo systemctl daemon-reexec
    sudo systemctl restart StatusOpenVPN.service
fi

# === Обновление logs.service (Environment) ===
if [ -f "$LOGS_SERVICE" ]; then
    if ! grep -qxF '^Environment=PYTHONIOENCODING=utf-8$' "$LOGS_SERVICE" || \
       ! grep -qxF '^Environment=LANG=C.UTF-8$' "$LOGS_SERVICE"; then
        sudo sed -i '/^Type=oneshot/a Environment=PYTHONIOENCODING=utf-8\nEnvironment=LANG=C.UTF-8' "$LOGS_SERVICE"
    fi
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
    read -e -p "Do you want to enable HTTPS? (y/N): " -i N enable_ssl
    if [[ "$enable_ssl" =~ ^[Yy]$ ]]; then
        HTTPS_ENABLED=1
        save_setup_var "HTTPS_ENABLED" "1"
    else
        HTTPS_ENABLED=0
        save_setup_var "HTTPS_ENABLED" "0"
    fi
fi

# Если HTTPS выбран, запрашиваем домен (или IP-only) и проверяем
if [[ "$HTTPS_ENABLED" -eq 1 ]]; then
    while true; do
        if [[ -z "$DOMAIN" ]]; then
            read -e -p "Enter your domain (example.com), or leave blank for IP-only (self-signed): " DOMAIN
        fi
        if [[ -z "$DOMAIN" ]]; then
            save_setup_var "DOMAIN" ""
            break
        fi
        if check_domain_ip "$DOMAIN"; then
            save_setup_var "DOMAIN" "$DOMAIN"
            break
        else
            echo -e "${RED}Domain does not point to this server. Try again.${RESET}"
            DOMAIN=""
        fi
    done

    if [[ -z "$DOMAIN" ]]; then
        # Режим HTTPS по IP (самоподписанный сертификат)
        CERT_PATH="/etc/nginx/ssl/selfsigned.crt"
        NGINX_CONF="/etc/nginx/sites-enabled/statusopenvpn-ip"
        if [[ -f "$CERT_PATH" ]] && openssl x509 -checkend 86400 -noout -in "$CERT_PATH" >/dev/null 2>&1 \
           && [[ -f "$NGINX_CONF" ]] && grep -q "# Created by StatusOpenVPN" "$NGINX_CONF"; then
            echo -e "${YELLOW}HTTPS already enabled for IP (self-signed).${RESET}"
            SERVER_URL="https://$(get_server_ip)/status/"
        else
            if [[ -f "$SSL_SCRIPT" ]]; then
                if echo "" | bash "$SSL_SCRIPT" -i; then
                    echo -e "${GREEN}HTTPS (IP-only) successfully enabled.${RESET}"
                    SERVER_URL="https://$(get_server_ip)/status/"
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
    else
        # Режим HTTPS по домену (Let's Encrypt)
        CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
        NGINX_CONF="/etc/nginx/sites-enabled/$DOMAIN"

        if [[ -f "$CERT_PATH" ]] && openssl x509 -checkend 86400 -noout -in "$CERT_PATH" >/dev/null 2>&1 \
           && [[ -f "$NGINX_CONF" ]] && grep -q "# Created by StatusOpenVPN" "$NGINX_CONF"; then
            echo -e "${YELLOW}HTTPS already enabled and valid for: $DOMAIN${RESET}"
            if ! openssl x509 -checkend 2592000 -noout -in "$CERT_PATH" 2>/dev/null; then
                echo -e "${YELLOW}Certificate expires within 30 days. Renewing...${RESET}"
                if sudo certbot renew --nginx --cert-name "$DOMAIN"; then
                    sudo systemctl reload nginx
                    echo -e "${GREEN}Certificate renewed.${RESET}"
                else
                    echo -e "${RED}Certificate renewal failed.${RESET}"
                fi
            fi
            SERVER_URL="https://$DOMAIN/status/"
        else
            if [[ -f "$SSL_SCRIPT" ]]; then
                if bash "$SSL_SCRIPT" -i "$DOMAIN"; then
                    echo -e "${GREEN}HTTPS successfully enabled for: $DOMAIN${RESET}"
                    SERVER_URL="https://$DOMAIN/status/"
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
fi

# === Обновление /location в nginx ===
if [[ "$HTTPS_ENABLED" -eq 1 ]]; then
    if [[ -n "$DOMAIN" ]]; then
        NGINX_CONF="/etc/nginx/sites-available/$DOMAIN"
        if [[ ! -f "$NGINX_CONF" ]] || ! grep -q "location /status/" "$NGINX_CONF"; then
            bash "$SSL_SCRIPT" -i "$DOMAIN"
        fi
    else
        NGINX_CONF="/etc/nginx/sites-available/statusopenvpn-ip"
        if [[ ! -f "$NGINX_CONF" ]] || ! grep -q "location /status/" "$NGINX_CONF"; then
            echo "" | bash "$SSL_SCRIPT" -i
        fi
    fi
fi

EXTERNAL_IP=$(curl -4 -s ifconfig.me)

if [[ -z "$SERVER_URL" ]]; then
    SERVER_URL="http://$EXTERNAL_IP:$PORT"
fi

# === Telegram Bot (состояние сохраняется) ===
if [[ "$BOT_ENABLED" -eq 1 ]]; then
    DEFAULT_INSTALL_BOT="Y"
else
    DEFAULT_INSTALL_BOT="N"
fi

if [[ "$BOT_ENABLED" -ne 1 ]]; then
    read -e -p "Would you like to install the Telegram bot service? (Y/N): " -i "$DEFAULT_INSTALL_BOT" INSTALL_BOT
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

# Проверка, установлен ли vnstat
if ! command -v vnstat &> /dev/null; then
    echo "📦 vnstat not found, installing..."
    sudo apt update && sudo apt install -y vnstat
    changes_made=true
else
    echo "🔄 vnstat found, updating to the latest version..."
    sudo apt update && sudo apt install --only-upgrade -y vnstat
fi

# Добавление интерфейсов
for iface in "${INTERFACES[@]}"; do
    # Проверяем, существует ли интерфейс в системе
    if ip link show "$iface" >/dev/null 2>&1; then
        # Проверяем, есть ли интерфейс в vnstat
        if ! sudo vnstat --iflist | grep -qw "$iface"; then
            echo "Adding interface $iface to vnstat..."
            sudo vnstat --add -i "$iface"
            changes_made=true
        fi
    else
        echo "Interface $iface does not exist. Skipping."
    fi
done

# Проверяем таймер
if [ -f "$OVERRIDE_FILE" ]; then
    if ! grep -q "$SLEEP_LINE" "$OVERRIDE_FILE"; then
        echo "⚙️  Adding delay line to existing override.conf..."
        echo -e "\n[Service]\n$SLEEP_LINE" | sudo tee -a "$OVERRIDE_FILE" >/dev/null
        changes_made=true
    fi
else
    echo "📁 Creating new override.conf..."
    sudo mkdir -p "$OVERRIDE_DIR"
    echo -e "[Service]\n$SLEEP_LINE" | sudo tee "$OVERRIDE_FILE" >/dev/null
    changes_made=true
fi


# Проверяем, есть ли файлы .db
if compgen -G "$SRC/*.db" > /dev/null; then
    echo "Migrating database files..."
    sudo systemctl stop wg_stats logs.timer StatusOpenVPN 2>/dev/null
    mkdir -p "$DST"
    mv "$SRC"/*.db "$DST"/ 2>/dev/null
    sudo systemctl start wg_stats logs.timer StatusOpenVPN 2>/dev/null
fi

# Перезагрузка systemd и запуск сервисов
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

# Включаем автозапуск и сразу запускаем службу vnstat
if ! systemctl is-enabled --quiet vnstat; then
    echo "Enabling vnstat autostart..."
    sudo systemctl enable --now vnstat
elif [ "$changes_made" = true ]; then
    echo "Restarting vnstat service due to configuration changes..."
    sudo systemctl restart vnstat
fi

sudo systemctl restart StatusOpenVPN
if systemctl cat telegram-bot &>/dev/null; then
    echo "Restarting telegram-bot service..."
    sudo systemctl restart telegram-bot
fi
sudo systemctl enable wg_stats
sudo systemctl restart wg_stats
sudo systemctl enable --now logs.timer
sudo systemctl restart logs.timer

echo "--------------------------------------------"
echo -e "Server is available at: \e[4;38;5;33m$SERVER_URL\e[0m"
echo "--------------------------------------------"

rm -f $TARGET_DIR/scripts/setup.sh
