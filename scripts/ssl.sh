#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RESET='\e[0m'

usage() {
  echo "Usage: $0 [OPTIONS] [DOMAIN]"
  echo
  echo "Options:"
  echo "  -i [DOMAIN]   Install Nginx + Certbot and configure HTTPS (domain optional)"
  echo "  -r [DOMAIN]   Remove Nginx configuration for domain"
  echo
  echo "Without domain: use self-signed certificate for access by IP (e.g. https://SERVER_IP/status/)"
  exit 1
}

if [[ "$EUID" -ne 0 ]]; then
    echo -e "${RED}❌ Please run as root${RESET}"
    exit 1
fi

if [[ $# -lt 1 ]]; then
    usage
fi

ACTION="$1"
DOMAIN="$2"

case "$ACTION" in
    -i|-r) ;;
    *) echo -e "${RED}Unknown option: $ACTION${RESET}"; usage ;;
esac

# Для -i домен опционален (без домена — самоподписанный сертификат по IP)
if [[ -z "$DOMAIN" ]]; then
    read -rp "Enter your domain (or leave blank for IP-only with self-signed certificate): " DOMAIN
fi

NO_DOMAIN=false
if [[ -z "$DOMAIN" ]]; then
    if [[ "$ACTION" == "-r" ]]; then
        echo -e "${RED}For -r specify domain or use: $0 -r statusopenvpn-ip${RESET}"
        exit 1
    fi
    NO_DOMAIN=true
elif [[ "$DOMAIN" == "statusopenvpn-ip" ]]; then
    NO_DOMAIN=true
fi

if [[ "$NO_DOMAIN" == true ]]; then
    SITE_ID="statusopenvpn-ip"
    CERT_PATH="/etc/nginx/ssl/selfsigned.crt"
    KEY_PATH="/etc/nginx/ssl/selfsigned.key"
    NGINX_CONF="/etc/nginx/sites-available/$SITE_ID"
    NGINX_LINK="/etc/nginx/sites-enabled/$SITE_ID"
else
    EMAIL="admin@$DOMAIN"
    CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
    KEY_PATH="/etc/letsencrypt/live/$DOMAIN/privkey.pem"
    NGINX_CONF="/etc/nginx/sites-available/$DOMAIN"
    NGINX_LINK="/etc/nginx/sites-enabled/$DOMAIN"
fi
SETUP_FILE="/root/web/setup"

SERVICE_FILE="/etc/systemd/system/StatusOpenVPN.service"
DEFAULT_PORT=1234
if [[ -f "$SERVICE_FILE" ]]; then
    FLASK_PORT=$(grep -oP '(?<=-b\s)(0\.0\.0\.0|127\.0\.0\.1)?:?\K[0-9]+' "$SERVICE_FILE" | head -n1)
    FLASK_PORT=${FLASK_PORT:-$DEFAULT_PORT}
else
    read -rp "Enter Flask app port (default: $DEFAULT_PORT): " FLASK_PORT
    FLASK_PORT=${FLASK_PORT:-$DEFAULT_PORT}
fi

save_setup_var() {
    local key=$1
    local value=$2
    if grep -q "^$key=" "$SETUP_FILE" 2>/dev/null; then
        sed -i "s|^$key=.*|$key=$value|" "$SETUP_FILE"
    else
        echo "$key=$value" >> "$SETUP_FILE"
    fi
}

update_service_ip() {
    local new_ip=$1
    if [[ -f "$SERVICE_FILE" ]]; then
        sed -i "s|ExecStart=/root/web/venv/bin/gunicorn -w 4 main:app -b .*:$FLASK_PORT|ExecStart=/root/web/venv/bin/gunicorn -w 4 main:app -b $new_ip:$FLASK_PORT|" "$SERVICE_FILE"
        systemctl daemon-reload
        systemctl restart StatusOpenVPN
        echo -e "${GREEN}Service updated ${RESET}"
    fi
}

check_nginx_configs() {
    local sites_available="/etc/nginx/sites-available"
    STATUSOPENVPN_CONFIGS=()
    OTHER_CONFIGS=()
    DOMAIN_CONFIG=""
    
    # Проверяем все конфигурации кроме default
    for config_file in "$sites_available"/*; do
        [[ ! -f "$config_file" ]] && continue
        local basename_config=$(basename "$config_file")
        [[ "$basename_config" == "default" ]] && continue
        
        # Проверяем первую строку на наличие комментария StatusOpenVPN
        local first_line=$(head -n 1 "$config_file" 2>/dev/null)
        if [[ "$first_line" == "# Created by StatusOpenVPN" ]]; then
            STATUSOPENVPN_CONFIGS+=("$config_file")
            # Проверяем, содержит ли имя файла домен
            if [[ "$basename_config" == "$DOMAIN" ]]; then
                DOMAIN_CONFIG="$config_file"
            fi
        else
            OTHER_CONFIGS+=("$config_file")
        fi
    done
}

install_nginx_certbot() {
    apt update
    apt install -y nginx openssl
    mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled

    if [[ "$NO_DOMAIN" == true ]]; then
        # Режим без домена: самоподписанный сертификат для доступа по IP
        echo -e "${YELLOW}🔧 Setting up HTTPS (IP-only, self-signed certificate)...${RESET}"
        mkdir -p /etc/nginx/ssl
        if [[ ! -f "$CERT_PATH" ]] || [[ ! -f "$KEY_PATH" ]]; then
            echo -e "${YELLOW}Generating self-signed certificate (valid 365 days)...${RESET}"
            openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
                -keyout "$KEY_PATH" \
                -out "$CERT_PATH" \
                -subj "/O=StatusOpenVPN/CN=$SERVER_IP" \
                -addext "subjectAltName = IP:$SERVER_IP"
            chmod 644 "$CERT_PATH"
            chmod 600 "$KEY_PATH"
            echo -e "${GREEN}Self-signed certificate created.${RESET}"
        else
            echo -e "${GREEN}Using existing self-signed certificate.${RESET}"
        fi
        local config_content
        config_content=$(cat <<'EOFIP'
# Created by StatusOpenVPN
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    server_name _;

    ssl_certificate     /etc/nginx/ssl/selfsigned.crt;
    ssl_certificate_key /etc/nginx/ssl/selfsigned.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location /status/ {
        proxy_pass http://127.0.0.1:FLASK_PORT_PLACEHOLDER;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Script-Name /status;

        proxy_redirect off;
    }
}
EOFIP
        )
        config_content="${config_content//FLASK_PORT_PLACEHOLDER/$FLASK_PORT}"
        echo "$config_content" > "$NGINX_CONF"
        ln -sf "$NGINX_CONF" "$NGINX_LINK"
        rm -f /etc/nginx/sites-enabled/default
        if nginx -t; then
            systemctl reload nginx
            echo -e "${GREEN}Nginx configuration created successfully.${RESET}"
        else
            echo -e "${RED}Nginx configuration test failed!${RESET}"
            exit 1
        fi
        save_setup_var "HTTPS_ENABLED" "1"
        save_setup_var "DOMAIN" ""
        SERVER_IP=$(curl -s http://checkip.amazonaws.com 2>/dev/null || hostname -I | awk '{print $1}')
        echo -e "${GREEN}HTTPS setup complete. Application available at: https://$SERVER_IP/status/${RESET}"
        echo -e "${YELLOW}Browser will show a security warning (self-signed cert) — this is normal.${RESET}"
        return 0
    fi

    echo -e "${YELLOW}🔧 Setting up HTTPS for $DOMAIN...${RESET}"
    SERVER_IP=$(curl -s http://checkip.amazonaws.com)
    DOMAIN_IP=$(getent ahostsv4 "$DOMAIN" | awk '{print $1}' | head -n1)
    if [[ "$SERVER_IP" != "$DOMAIN_IP" ]]; then
        echo -e "${RED}Domain IP ($DOMAIN_IP) does not match server IP ($SERVER_IP).${RESET}"
        exit 1
    fi
    echo -e "${GREEN}Domain resolves correctly.${RESET}"

    apt install -y certbot python3-certbot-nginx

    if certbot certificates | grep -q "Domains: $DOMAIN"; then
        DAYS_LEFT=$(certbot certificates 2>/dev/null | awk -v domain="$DOMAIN" '
            $0 ~ "Domains: "domain {found=1}
            found && /VALID:/ {
                match($0, /\(VALID: ([0-9]+) days\)/, a)
                if (a[1] != "") print a[1]
                exit
            }')
        if [[ -z "$DAYS_LEFT" || "$DAYS_LEFT" -le 30 ]]; then
            echo -e "${YELLOW}Renewing certificate...${RESET}"
            if ! certbot renew --nginx --cert-name "$DOMAIN"; then
                echo -e "${RED}Renewal failed.${RESET}"
                save_setup_var "HTTPS_ENABLED" "0"
                exit 1
            fi
        else
            echo -e "${GREEN}Certificate valid for $DAYS_LEFT days.${RESET}"
        fi
    else
        echo -e "${YELLOW}Obtaining new certificate...${RESET}"
        read -rp "Enter email for Let's Encrypt (leave blank to skip): " EMAIL_INPUT
        EMAIL=${EMAIL_INPUT:-$EMAIL}
        if [[ -z "$EMAIL_INPUT" ]]; then
            certbot --nginx -d "$DOMAIN" --register-unsafely-without-email --agree-tos || { save_setup_var "HTTPS_ENABLED" "0"; exit 1; }
        else
            certbot --nginx -d "$DOMAIN" --email "$EMAIL" --agree-tos || { save_setup_var "HTTPS_ENABLED" "0"; exit 1; }
        fi
    fi

    # Проверяем существующие конфигурации
    check_nginx_configs

    local update_existing=false
    local disable_default=false

    # Обновить существующий конфиг StatusOpenVPN для домена или создать новый
    if [[ -n "$DOMAIN_CONFIG" && ${#STATUSOPENVPN_CONFIGS[@]} -eq 1 && ${#OTHER_CONFIGS[@]} -eq 0 ]]; then
        echo -e "${YELLOW}Found existing StatusOpenVPN config for $DOMAIN. Updating it.${RESET}"
        update_existing=true
        disable_default=true
    elif [[ ${#STATUSOPENVPN_CONFIGS[@]} -eq 0 && ${#OTHER_CONFIGS[@]} -eq 0 ]]; then
        echo -e "${YELLOW}No existing configurations found. Creating new config.${RESET}"
        disable_default=true
    else
        echo -e "${YELLOW}Creating/updating Nginx config for $DOMAIN.${RESET}"
    fi

    # Единая конфигурация: location всегда /status/
    local config_content
    config_content=$(cat <<EOF
# Created by StatusOpenVPN
server {
    listen 80;
    server_name $DOMAIN;
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    server_name $DOMAIN;

    ssl_certificate     $CERT_PATH;
    ssl_certificate_key $KEY_PATH;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location /status/ {
        proxy_pass http://127.0.0.1:$FLASK_PORT;

        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Script-Name /status;

        proxy_redirect off;
    }
}
EOF
    )

    if [[ "$update_existing" == true ]]; then
        echo "$config_content" > "$DOMAIN_CONFIG"
        NGINX_CONF="$DOMAIN_CONFIG"
    else
        echo "$config_content" > "$NGINX_CONF"
    fi

    # Создаём или обновляем симлинк
    ln -sf "$NGINX_CONF" "$NGINX_LINK"
    
    # Отключаем default если нужно
    if [[ "$disable_default" == true ]]; then
        local default_link="/etc/nginx/sites-enabled/default"
        if [[ -L "$default_link" ]]; then
            rm -f "$default_link"
            echo -e "${GREEN}Default site disabled.${RESET}"
        fi
    fi
    
    # Проверяем конфигурацию и перезагружаем nginx
    if nginx -t; then
        systemctl reload nginx
        echo -e "${GREEN}Nginx configuration ${update_existing:+updated}${update_existing:-created} successfully.${RESET}"
    else
        echo -e "${RED}Nginx configuration test failed!${RESET}"
        exit 1
    fi

    save_setup_var "HTTPS_ENABLED" "1"
    save_setup_var "DOMAIN" "$DOMAIN"
    echo -e "${GREEN}HTTPS setup complete. Application available at: https://$DOMAIN/status/${RESET}"
}

remove_nginx_site() {
    echo -e "${YELLOW}Removing Nginx configuration for $DOMAIN...${RESET}"

    if [[ -f "$NGINX_CONF" ]]; then
        first_line=$(head -n 1 "$NGINX_CONF")
        if [[ "$first_line" == "# Created by StatusOpenVPN" ]]; then
            [[ -L "$NGINX_LINK" ]] && rm -f "$NGINX_LINK"

            if nginx -t 2>/dev/null; then
                systemctl reload nginx
            else
                echo -e "${RED}Nginx config test failed. Skipping reload.${RESET}"
            fi

            rm -f "$NGINX_CONF"
            save_setup_var "HTTPS_ENABLED" "0"
            echo -e "${GREEN}Nginx configuration removed.${RESET}"
        else
            echo -e "${RED}$NGINX_CONF was not created by StatusOpenVPN. Skipping.${RESET}"
        fi
    else
        echo -e "${YELLOW}$NGINX_CONF does not exist. Nothing to remove.${RESET}"
    fi
}

case "$ACTION" in
    -i)
        install_nginx_certbot
        update_service_ip "127.0.0.1"
        ;;
    -r)
        remove_nginx_site
        update_service_ip "0.0.0.0"
        ;;
    *) usage ;;
esac
