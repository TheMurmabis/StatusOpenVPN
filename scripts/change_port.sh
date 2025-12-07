#!/bin/bash

# Путь к директории проекта и systemd-сервису
TARGET_DIR="/root/web"
SETUP_FILE="$TARGET_DIR/setup"
SERVICE_FILE="/etc/systemd/system/StatusOpenVPN.service"

# Проверка, что сервисный файл существует
if [ ! -f "$SERVICE_FILE" ]; then
    echo "Error: Service file $SERVICE_FILE not found."
    exit 1
fi

# Проверка наличия setup-файла
if [ -f "$SETUP_FILE" ]; then
    DOMAIN=$(grep -E '^DOMAIN=' "$SETUP_FILE" | cut -d '=' -f2)
    HTTPS_ENABLED=$(grep -E '^HTTPS_ENABLED=' "$SETUP_FILE" | cut -d '=' -f2)
else
    DOMAIN=""
    HTTPS_ENABLED=0
fi

# Функция проверки свободности порта
check_port_free() {
    local PORT=$1
    if ! ss -tuln | grep -q ":$PORT "; then
        return 0  # Порт свободен
    else
        return 1  # Порт занят
    fi
}

# Запрос нового порта
while true; do
    read -p "Enter a new port number (1-65535): " NEW_PORT
    if [[ "$NEW_PORT" =~ ^[0-9]+$ ]] && [ "$NEW_PORT" -ge 1 ] && [ "$NEW_PORT" -le 65535 ]; then
        if check_port_free "$NEW_PORT"; then
            echo "Port $NEW_PORT is free. Applying changes..."
            break
        else
            echo "Port $NEW_PORT is already in use."
        fi
    else
        echo "Invalid port number."
    fi
done

# Замена порта в service-файле
sed -i -E "s/(:)[0-9]+/\1$NEW_PORT/" "$SERVICE_FILE"

# Перезапуск сервиса
echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "Restarting StatusOpenVPN service..."
systemctl restart StatusOpenVPN

# Если включён HTTPS и указан домен — обновляем конфиг Nginx
if [ "$HTTPS_ENABLED" = "1" ] && [ -n "$DOMAIN" ]; then
    NGINX_CONF="/etc/nginx/sites-enabled/$DOMAIN"
    CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
    KEY_PATH="/etc/letsencrypt/live/$DOMAIN/privkey.pem"

    echo "HTTPS mode enabled for domain: $DOMAIN"
    echo "Updating Nginx configuration..."

    cat > "$NGINX_CONF" <<EOF
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

    location / {
        proxy_pass http://127.0.0.1:$NEW_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF

    # Проверка конфигурации и перезапуск nginx
    nginx -t && systemctl reload nginx
fi

# Получаем внешний IP
EXTERNAL_IP=$(curl -4 -s ifconfig.me)

echo "--------------------------------------------"
if [ "$HTTPS_ENABLED" = "1" ] && [ -n "$DOMAIN" ]; then
    echo -e "Service is now available at: \e[4;38;5;33mhttps://$DOMAIN\e[0m"
else
    echo -e "Service is now available at: \e[4;38;5;33mhttp://$EXTERNAL_IP:$NEW_PORT\e[0m"
fi
echo "--------------------------------------------"
