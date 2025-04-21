#!/bin/bash

# Путь к директории проекта и systemd-сервису
TARGET_DIR="/root/web"
SERVICE_FILE="/etc/systemd/system/StatusOpenVPN.service"

# Проверка, что сервисный файл существует
if [ ! -f "$SERVICE_FILE" ]; then
    echo "Error: Service file $SERVICE_FILE not found."
    exit 1
fi

# Функция для проверки, свободен ли порт
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

# Проверка IP
EXTERNAL_IP=$(curl -4 -s ifconfig.me)

echo "--------------------------------------------"
echo -e "Service is now available at: \e[4;38;5;33mhttp://$EXTERNAL_IP:$NEW_PORT\e[0m"
echo "--------------------------------------------"
