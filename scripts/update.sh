#!/bin/bash 

# Обработка ошибок
set -e

# Переменные
TARGET_DIR="/root/web"  # Папка, где уже клонирован репозиторий
DEFAULT_PORT=1234  # Порт по умолчанию

# Получение текущего порта из файла сервиса, если он уже установлен
SERVICE_FILE="/etc/systemd/system/StatusOpenVPN.service"
if [ -f "$SERVICE_FILE" ]; then
    CURRENT_PORT=$(grep -oP '(?<=-b 0.0.0.0:)[0-9]+' "$SERVICE_FILE" || echo "$DEFAULT_PORT")
else
    CURRENT_PORT=$DEFAULT_PORT
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

# Запрос на изменение текущего порта
read -e -p "Would you like to change the current port $CURRENT_PORT? (Y/N): " -i N CHANGE_PORT

if [[ "$CHANGE_PORT" =~ ^[Yy]$ ]]; then
    # Остановка сервиса
    echo "Stopping StatusOpenVPN service..."
    sudo systemctl stop StatusOpenVPN
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
    PORT=$CURRENT_PORT
    echo "Using current port $PORT."
fi

# Обновление репозитория
echo "Updating repository in $TARGET_DIR..."
cd $TARGET_DIR
git reset --hard  # Отмена всех локальных изменений
git fetch origin && git reset --hard origin/main

# rm src/openvpn_logs.db

#Активация виртуального окружения
echo "Activating virtual environment..."
source venv/bin/activate

# Проверка и установка новых зависимостей
if [ -f "requirements.txt" ]; then
    echo "Installing any new requirements from requirements.txt..."
    pip install -r requirements.txt
else
    echo "requirements.txt not found, skipping this step."
fi

# Обновление конфигурации порта в systemd-сервисе
if [ -f "$SERVICE_FILE" ]; then
    echo "Updating port configuration in systemd service file."
    sudo sed -i "s/-b 0.0.0.0:[0-9]*/-b 0.0.0.0:$PORT/" $SERVICE_FILE
else
    echo "Creating systemd service file at $SERVICE_FILE..."
    cat <<EOF | sudo tee $SERVICE_FILE
[Unit]
Description=Gunicorn instance to serve my Flask app
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

# Создание и настройка logs.service
LOGS_SERVICE_FILE="/etc/systemd/system/logs.service"
cat <<EOF | sudo tee $LOGS_SERVICE_FILE
[Unit]
Description=Run logs.py script

[Service]
Type=oneshot
ExecStart=$TARGET_DIR/venv/bin/python $TARGET_DIR/src/logs.py
EOF

# Создание и настройка logs.timer
LOGS_TIMER_FILE="/etc/systemd/system/logs.timer"
cat <<EOF | sudo tee $LOGS_TIMER_FILE
[Unit]
Description=Run logs.py every 30 seconds

[Timer]
OnBootSec=30s
OnUnitActiveSec=30s
Unit=logs.service

[Install]
WantedBy=timers.target
EOF

# Перезагрузка systemd и перезапуск сервиса
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

# Перезапуск сервиса
echo "Restarting StatusOpenVPN service..."
sudo systemctl restart StatusOpenVPN

# Активация и запуск таймера
sudo systemctl enable --now logs.timer

# Получение внешнего IP-адреса сервера
EXTERNAL_IP=$(curl -4 -s ifconfig.me)

# Вывод информации об обновлении
echo "--------------------------------------------"
echo -e "\e[32mUpdate completed successfully\e[0m"
echo "--------------------------------------------"
echo -e "Server is available at: \e[4;38;5;33mhttp://$EXTERNAL_IP:$PORT\e[0m"
echo "--------------------------------------------"

rm -f $TARGET_DIR/scripts/setup.sh 
