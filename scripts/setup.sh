#!/bin/bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RESET='\e[0m'

TARGET_DIR="/root/web"
SRC="$TARGET_DIR/src"
DST="$TARGET_DIR/src/databases"
DEFAULT_PORT=1234
ENV_FILE="$TARGET_DIR/src/.env"
SERVICE_FILE="/etc/systemd/system/StatusOpenVPN.service"
LOGS_SERVICE="/etc/systemd/system/logs.service"
LOGS_TIMER="/etc/systemd/system/logs.timer"
WG_STATS="/etc/systemd/system/wg_stats.service"
BOT_SERVICE="/etc/systemd/system/telegram-bot.service"
SETUP_FILE="$TARGET_DIR/setup"
SSL_SCRIPT="$TARGET_DIR/scripts/ssl.sh"
REPO_URL="https://github.com/TheMurmabis/StatusOpenVPN.git"
SERVER_URL=""
INTERFACES=("antizapret-tcp" "vpn-tcp" "antizapret-udp" "vpn-udp" "vpn" "antizapret")

OVERRIDE_DIR="/etc/systemd/system/vnstat.service.d"
OVERRIDE_FILE="$OVERRIDE_DIR/override.conf"
SLEEP_LINE="ExecStartPre=/bin/sleep 10"
changes_made=false

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

is_installed() {
    [[ -f "$SERVICE_FILE" && -d "$TARGET_DIR/venv" ]]
}

install_python_venv() {
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo "Detected Python version: $PYTHON_VERSION"

    if ! dpkg -s "python${PYTHON_VERSION}-venv" >/dev/null 2>&1; then
        echo "Installing python${PYTHON_VERSION}-venv..."
        run_as_root apt update && run_as_root apt install -y "python${PYTHON_VERSION}-venv" || { echo -e "${RED}❌ Failed to install python${PYTHON_VERSION}-venv${RESET}"; exit 1; }
    else
        echo "python${PYTHON_VERSION}-venv is already installed."
    fi
}

check_port_free() {
    local PORT=$1
    if ! ss -tuln | grep -q ":$PORT "; then
        return 0
    else
        return 1
    fi
}

save_setup_var() {
    local key=$1
    local value=$2
    if grep -q "^$key=" "$SETUP_FILE" 2>/dev/null; then
        sed -i "s|^$key=.*|$key=$value|" "$SETUP_FILE"
    else
        echo "$key=$value" >> "$SETUP_FILE"
    fi
}

load_setup_file() {
    if [[ -f "$SETUP_FILE" ]]; then
        source "$SETUP_FILE" 2>/dev/null || true
    fi
}

setup_var_saved() {
    local key=$1
    grep -q "^${key}=" "$SETUP_FILE" 2>/dev/null
}

load_server_url_from_setup() {
    if [[ -f "$SETUP_FILE" ]]; then
        local setup_server_url
        setup_server_url=$(awk -F= '/^SERVER_URL=/{sub(/^SERVER_URL=/,""); print; exit}' "$SETUP_FILE")
        if [[ -n "$setup_server_url" ]]; then
            SERVER_URL="$setup_server_url"
        fi
    fi
}

get_server_ip() { curl -s http://checkip.amazonaws.com; }

check_domain_ip() {
    local domain="$1"
    local server_ip
    server_ip=$(get_server_ip)
    local domain_ip
    domain_ip=$(getent ahostsv4 "$domain" | awk '{print $1}' | head -n1)
    [[ "$server_ip" == "$domain_ip" ]]
}

is_silent_mode() {
    [[ "${STATUSOPENVPN_SILENT:-}" == "1" ]]
}

ask_port() {
    local current_port=$1
    local prompt_text=$2

    if is_silent_mode; then
        PORT=$current_port
        echo "Using port $PORT."
        return
    fi

    read -e -p "$prompt_text $current_port? (Y/N): " -i N CHANGE_PORT
    if [[ "$CHANGE_PORT" =~ ^[Yy]$ ]]; then
        if is_installed; then
            run_as_root systemctl stop StatusOpenVPN 2>/dev/null || true
        fi
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
        PORT=$current_port
        echo "Using port $PORT."
    fi
}

create_main_service() {
    local secret_key=$1
    echo "Creating systemd service file at $SERVICE_FILE..."
    cat <<EOF | run_as_root tee $SERVICE_FILE >/dev/null
[Unit]
Description=Gunicorn instance to serve StatusOpenVPN
After=network.target

[Service]
User=root
Group=www-data
WorkingDirectory=$TARGET_DIR
Environment="PATH=$TARGET_DIR/venv/bin"
Environment="SECRET_KEY=$secret_key"
ExecStart=$TARGET_DIR/venv/bin/gunicorn -w 4 main:app -b 0.0.0.0:$PORT

[Install]
WantedBy=multi-user.target
EOF
}

create_logs_units() {
    cat <<EOF | run_as_root tee $LOGS_SERVICE >/dev/null
[Unit]
Description=Run logs.py script

[Service]
Type=oneshot
Environment=PYTHONIOENCODING=utf-8
Environment=LANG=C.UTF-8
ExecStart=$TARGET_DIR/venv/bin/python $TARGET_DIR/src/logs.py
EOF

    cat <<EOF | run_as_root tee $LOGS_TIMER >/dev/null
[Unit]
Description=Run logs.py every 30 seconds

[Timer]
OnBootSec=30s
OnUnitActiveSec=30s
Unit=logs.service

[Install]
WantedBy=timers.target
EOF
}

create_wg_stats_service() {
    cat <<EOF | run_as_root tee $WG_STATS >/dev/null
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
}

create_bot_service() {
    cat <<EOF | run_as_root tee $BOT_SERVICE >/dev/null
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
}

setup_telegram_bot() {
    load_setup_file
    BOT_ENABLED=${BOT_ENABLED:-0}

    if [[ "$BOT_ENABLED" -eq 1 ]]; then
        echo -e "${GREEN}Telegram bot already enabled.${RESET}"
        return
    fi

    if is_silent_mode; then
        return
    fi

    local default_install_bot=Y
    if setup_var_saved BOT_ENABLED && [[ "$BOT_ENABLED" -eq 0 ]]; then
        default_install_bot=N
    fi

    read -e -p "Would you like to install the Telegram bot service? (Y/N): " -i "$default_install_bot" INSTALL_BOT
    if [[ "$INSTALL_BOT" =~ ^[Yy]$ ]]; then
        read -rsp "Enter Telegram bot API token: " BOT_TOKEN_INPUT
        echo
        if [[ -z "$BOT_TOKEN_INPUT" ]]; then
            echo -e "${RED}Bot token cannot be empty.${RESET}"
            exit 1
        fi
        echo "Creating Telegram bot service..."
        create_bot_service

        if [ ! -f "$ENV_FILE" ]; then
            echo "Creating .env file..."
            cat <<EOF > $ENV_FILE
BOT_TOKEN=$BOT_TOKEN_INPUT
ADMIN_ID=<Enter your user ID>
EOF
        else
            escaped_bot_token=$(printf '%s' "$BOT_TOKEN_INPUT" | sed 's/[\/&]/\\&/g')
            if grep -q '^BOT_TOKEN=' "$ENV_FILE"; then
                sed -i "s/^BOT_TOKEN=.*/BOT_TOKEN=$escaped_bot_token/" "$ENV_FILE"
            else
                echo "BOT_TOKEN=$BOT_TOKEN_INPUT" >> "$ENV_FILE"
            fi
        fi

        BOT_ENABLED=1
        save_setup_var "BOT_ENABLED" "1"
        run_as_root systemctl enable telegram-bot
    else
        BOT_ENABLED=0
        save_setup_var "BOT_ENABLED" "0"
    fi
}

setup_https() {
    load_setup_file
    HTTPS_ENABLED=${HTTPS_ENABLED:-0}

    if [[ "$HTTPS_ENABLED" -ne 1 ]]; then
        if is_silent_mode; then
            return
        fi
        read -e -p "Do you want to enable HTTPS? (y/N): " -i N enable_ssl
        if [[ "$enable_ssl" =~ ^[Yy]$ ]]; then
            HTTPS_ENABLED=1
            save_setup_var "HTTPS_ENABLED" "1"
        else
            HTTPS_ENABLED=0
            save_setup_var "HTTPS_ENABLED" "0"
        fi
    fi

    if [[ "$HTTPS_ENABLED" -ne 1 ]]; then
        return
    fi

    while true; do
        if [[ -z "$DOMAIN" ]]; then
            if is_silent_mode; then
                save_setup_var "DOMAIN" ""
                break
            fi
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
            echo -e "${RED}❌ Domain does not point to this server. Try again.${RESET}"
            DOMAIN=""
        fi
    done

    if [[ -z "$DOMAIN" ]]; then
        local CERT_PATH="/etc/nginx/ssl/selfsigned.crt"
        local NGINX_CONF="/etc/nginx/sites-enabled/statusopenvpn-ip"
        if [[ -f "$CERT_PATH" ]] && openssl x509 -checkend 86400 -noout -in "$CERT_PATH" >/dev/null 2>&1 \
           && [[ -f "$NGINX_CONF" ]] && grep -q "# Created by StatusOpenVPN" "$NGINX_CONF"; then
            echo -e "${YELLOW}✅ HTTPS already enabled for IP (self-signed).${RESET}"
            SERVER_URL="https://$(get_server_ip)/status/"
        else
            if [[ -f "$SSL_SCRIPT" ]]; then
                if echo "" | bash "$SSL_SCRIPT" -i; then
                    echo -e "${GREEN}✅ HTTPS (IP-only) successfully enabled.${RESET}"
                    load_server_url_from_setup
                    if [[ -z "$SERVER_URL" ]]; then
                        SERVER_URL="https://$(get_server_ip)/status/"
                    fi
                else
                    echo -e "${RED}❌ SSL setup failed.${RESET}"
                    HTTPS_ENABLED=0
                    save_setup_var "HTTPS_ENABLED" "0"
                fi
            else
                echo -e "${RED}❌ SSL script not found.${RESET}"
                HTTPS_ENABLED=0
                save_setup_var "HTTPS_ENABLED" "0"
            fi
        fi
    else
        local CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
        local NGINX_CONF="/etc/nginx/sites-enabled/$DOMAIN"

        if [[ -f "$CERT_PATH" ]] && openssl x509 -checkend 86400 -noout -in "$CERT_PATH" >/dev/null 2>&1 \
           && [[ -f "$NGINX_CONF" ]] && grep -q "# Created by StatusOpenVPN" "$NGINX_CONF"; then
            echo -e "${YELLOW}✅ HTTPS already enabled and valid for: $DOMAIN${RESET}"
            if ! openssl x509 -checkend 2592000 -noout -in "$CERT_PATH" 2>/dev/null; then
                echo -e "${YELLOW}Certificate expires within 30 days. Renewing...${RESET}"
                if run_as_root certbot renew --nginx --cert-name "$DOMAIN"; then
                    run_as_root systemctl reload nginx
                    echo -e "${GREEN}Certificate renewed.${RESET}"
                else
                    echo -e "${RED}Certificate renewal failed.${RESET}"
                fi
            fi
            SERVER_URL="https://$DOMAIN/status/"
        else
            if [[ -f "$SSL_SCRIPT" ]]; then
                if bash "$SSL_SCRIPT" -i "$DOMAIN"; then
                    echo -e "${GREEN}✅ HTTPS successfully enabled for: $DOMAIN${RESET}"
                    load_server_url_from_setup
                    if [[ -z "$SERVER_URL" ]]; then
                        SERVER_URL="https://$DOMAIN/status/"
                    fi
                else
                    echo -e "${RED}❌ SSL setup failed.${RESET}"
                    HTTPS_ENABLED=0
                    save_setup_var "HTTPS_ENABLED" "0"
                fi
            else
                echo -e "${RED}❌ SSL script not found.${RESET}"
                HTTPS_ENABLED=0
                save_setup_var "HTTPS_ENABLED" "0"
            fi
        fi
    fi
    return 0
}

refresh_nginx_location() {
    if [[ "$HTTPS_ENABLED" -ne 1 ]]; then
        return
    fi
    if [[ -n "$DOMAIN" ]]; then
        local NGINX_CONF="/etc/nginx/sites-available/$DOMAIN"
        if [[ ! -f "$NGINX_CONF" ]] || ! grep -q "location /status/" "$NGINX_CONF"; then
            bash "$SSL_SCRIPT" -i "$DOMAIN"
        fi
    else
        local NGINX_CONF="/etc/nginx/sites-available/statusopenvpn-ip"
        if [[ ! -f "$NGINX_CONF" ]] || ! grep -q "location /status/" "$NGINX_CONF"; then
            echo "" | bash "$SSL_SCRIPT" -i
        fi
    fi
}

setup_vnstat() {
    if ! command -v vnstat &> /dev/null; then
        echo "📦 vnstat not found, installing..."
        run_as_root apt update && run_as_root apt install -y vnstat
        changes_made=true
    else
        echo "🔄 vnstat found, updating to the latest version..."
        run_as_root apt update && run_as_root apt install --only-upgrade -y vnstat
    fi

    for iface in "${INTERFACES[@]}"; do
        if ip link show "$iface" >/dev/null 2>&1; then
            if ! run_as_root vnstat --iflist | grep -qw "$iface"; then
                echo "Adding interface $iface to vnstat..."
                run_as_root vnstat --add -i "$iface"
                changes_made=true
            fi
        else
            echo "Interface $iface does not exist. Skipping."
        fi
    done

    if [ -f "$OVERRIDE_FILE" ]; then
        if ! grep -q "$SLEEP_LINE" "$OVERRIDE_FILE"; then
            echo "⚙️  Adding delay line to existing override.conf..."
            echo -e "\n[Service]\n$SLEEP_LINE" | run_as_root tee -a "$OVERRIDE_FILE" >/dev/null
            changes_made=true
        fi
    else
        echo "📁 Creating new override.conf..."
        run_as_root mkdir -p "$OVERRIDE_DIR"
        echo -e "[Service]\n$SLEEP_LINE" | run_as_root tee "$OVERRIDE_FILE" >/dev/null
        changes_made=true
    fi
}

restart_vnstat_if_needed() {
    if ! systemctl is-enabled --quiet vnstat; then
        echo "Enabling vnstat autostart..."
        run_as_root systemctl enable --now vnstat
    elif [ "$changes_made" = true ]; then
        echo "Restarting vnstat service due to configuration changes..."
        run_as_root systemctl restart vnstat
    fi
}

install_flow() {
    echo -e "${GREEN}Running installation...${RESET}"

    ask_port "$DEFAULT_PORT" "Would you like to change the default port"

    if [ ! -d "$TARGET_DIR/.git" ]; then
        echo "Cloning repository into $TARGET_DIR..."
        git clone "$REPO_URL" "$TARGET_DIR"
    else
        echo "Repository already exists in $TARGET_DIR, skipping clone."
    fi
    cd "$TARGET_DIR"

    install_python_venv
    if [ ! -d "$TARGET_DIR/venv" ]; then
        echo "Creating virtual environment..."
        python3 -m venv venv
    fi
    source venv/bin/activate

    if [ -f "requirements.txt" ]; then
        echo "Installing requirements..."
        pip install -q -r requirements.txt > /dev/null
    fi

    local SECRET_KEY
    SECRET_KEY=$(openssl rand -hex 32)
    create_main_service "$SECRET_KEY"
    create_logs_units
    create_wg_stats_service

    setup_telegram_bot

    echo "Running initial admin setup..."
    local ADMIN_PASS
    ADMIN_PASS=$(PYTHONIOENCODING=utf-8 python3 -c "from main import add_admin; print(add_admin())")

    setup_https
    setup_vnstat

    echo "Reloading systemd daemon..."
    run_as_root systemctl daemon-reload

    restart_vnstat_if_needed

    run_as_root systemctl enable StatusOpenVPN wg_stats logs.timer
    run_as_root systemctl start StatusOpenVPN wg_stats logs.timer

    if [[ "$BOT_ENABLED" -eq 1 ]]; then
        run_as_root systemctl enable telegram-bot
        run_as_root systemctl start telegram-bot 2>/dev/null || true
    fi

    local EXTERNAL_IP
    EXTERNAL_IP=$(curl -4 -s ifconfig.me)
    if [[ -z "$SERVER_URL" ]]; then
        SERVER_URL="http://$EXTERNAL_IP:$PORT"
    fi

    echo "--------------------------------------------"
    echo -e "${GREEN}✅ Setup completed successfully${RESET}"
    echo "--------------------------------------------"
    echo -e "Server is available at: \e[4;38;5;33m$SERVER_URL\e[0m"
    echo -e "Admin login: ${GREEN}admin${RESET}"
    echo -e "Admin password: ${GREEN}$ADMIN_PASS${RESET}"
    echo "--------------------------------------------"
}

update_flow() {
    echo -e "${GREEN}🔄 Running update...${RESET}"

    local CURRENT_PORT
    if [ -f "$SERVICE_FILE" ]; then
        CURRENT_PORT=$(grep -oP '(?<=-b 0.0.0.0:)[0-9]+' "$SERVICE_FILE" || echo "$DEFAULT_PORT")
    else
        CURRENT_PORT=$DEFAULT_PORT
    fi

    ask_port "$CURRENT_PORT" "Would you like to change the current port"

    cd "$TARGET_DIR"
    if [ -d "$TARGET_DIR/.git" ]; then
        git reset --hard
        git fetch origin --tags
        if [[ -n "${STATUSOPENVPN_UPDATE_TAG:-}" ]]; then
            echo "Checking out tag ${STATUSOPENVPN_UPDATE_TAG}..."
            git checkout -f "${STATUSOPENVPN_UPDATE_TAG}"
        else
            git reset --hard origin/main
        fi
    else
        echo -e "${YELLOW}⚠️  Git repository not found in $TARGET_DIR, skipping git update.${RESET}"
    fi

    if [ ! -d "$TARGET_DIR/venv" ]; then
        install_python_venv
        python3 -m venv venv
    fi
    source venv/bin/activate
    if [ -f "requirements.txt" ]; then
        pip install -q -r requirements.txt > /dev/null
    fi

    if [ -f "$SERVICE_FILE" ]; then
        run_as_root sed -i "s/-b 0.0.0.0:[0-9]*/-b 0.0.0.0:$PORT/" "$SERVICE_FILE"
    else
        local SECRET_KEY
        SECRET_KEY=$(openssl rand -hex 32)
        create_main_service "$SECRET_KEY"
    fi

    if ! grep -q 'SECRET_KEY=' "$SERVICE_FILE"; then
        local SECRET_KEY
        SECRET_KEY=$(openssl rand -hex 32)
        run_as_root sed -i "/^Environment=\"PATH=/a Environment=\"SECRET_KEY=$SECRET_KEY\"" "$SERVICE_FILE"
        run_as_root systemctl daemon-reexec
        run_as_root systemctl restart StatusOpenVPN.service
    fi

    [ ! -f "$LOGS_SERVICE" ] || [ ! -f "$LOGS_TIMER" ] && create_logs_units
    [ ! -f "$WG_STATS" ] && create_wg_stats_service

    setup_https
    refresh_nginx_location

    local EXTERNAL_IP
    EXTERNAL_IP=$(curl -4 -s ifconfig.me)
    if [[ -z "$SERVER_URL" ]]; then
        SERVER_URL="http://$EXTERNAL_IP:$PORT"
    fi

    setup_telegram_bot
    setup_vnstat

    if compgen -G "$SRC/*.db" > /dev/null; then
        echo "Migrating database files..."
        run_as_root systemctl stop wg_stats logs.timer StatusOpenVPN 2>/dev/null || true
        mkdir -p "$DST"
        mv "$SRC"/*.db "$DST"/ 2>/dev/null || true
        run_as_root systemctl start wg_stats logs.timer StatusOpenVPN 2>/dev/null || true
    fi

    echo "Reloading systemd daemon..."
    run_as_root systemctl daemon-reload

    restart_vnstat_if_needed

    run_as_root systemctl restart StatusOpenVPN
    if systemctl cat telegram-bot &>/dev/null; then
        echo "Restarting telegram-bot service..."
        run_as_root systemctl restart telegram-bot
    fi
    run_as_root systemctl enable wg_stats
    run_as_root systemctl restart wg_stats
    run_as_root systemctl enable --now logs.timer
    run_as_root systemctl restart logs.timer logs.service

    echo "--------------------------------------------"
    echo -e "${GREEN}✅ Update completed successfully${RESET}"
    echo -e "Server is available at: \e[4;38;5;33m$SERVER_URL\e[0m"
    echo "--------------------------------------------"
}

main() {
    if is_installed; then
        update_flow
    else
        install_flow
    fi
}

main "$@"
