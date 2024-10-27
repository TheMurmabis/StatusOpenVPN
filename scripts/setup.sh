#!/bin/bash

# Обработка ошибок
set -e

# Переменные
TARGET_DIR="/root/web"  # Папка, куда будет клонирован репозиторий
DEFAULT_PORT=1234  # Порт по умолчанию

# Функция для проверки, свободен ли порт
check_port_free() {
    local PORT=$1
    if ! ss -tuln | grep -q ":$PORT "; then
        return 0  # Порт свободен
    else
        return 1  # Порт занят
    fi
}

# Запрос на изменение порта
read -e -p "Would you like to change the default port $DEFAULT_PORT? (Y/N): " -i N CHANGE_PORT

if [[ "$CHANGE_PORT" =~ ^[Yy]$ ]]; then
    while true; do
        read -p "Please enter a new port number: " NEW_PORT

        # Проверка, что введённый порт является числом и в диапазоне допустимых значений
        if [[ "$NEW_PORT" =~ ^[0-9]+$ ]] && [ "$NEW_PORT" -ge 1 ] && [ "$NEW_PORT" -le 65535 ]; then
            # Проверка, что порт свободен
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

# Клонирование репозитория в папку web
echo "Cloning repository into $TARGET_DIR..."
git clone https://github.com/TheMurmabis/StatusOpenVPN.git $TARGET_DIR

# Переход в директорию проекта
cd $TARGET_DIR

# Установка необходимого пакета для создания виртуальных окружений Python
echo "Installing python3.12-venv..."
apt update && apt install -y python3.12-venv

# Создание виртуального окружения
echo "Creating virtual environment..."
python3 -m venv venv

# Активация виртуального окружения
echo "Activating virtual environment..."
source venv/bin/activate

# Установка зависимостей из requirements.txt, если файл существует
if [ -f "requirements.txt" ]; then
    echo "Installing requirements from requirements.txt..."
    pip install -r requirements.txt
else
    echo "requirements.txt not found, skipping this step."
fi

# Создание и настройка systemd-сервиса
SERVICE_FILE="/etc/systemd/system/StatusOpenVPN.service"
echo "Creating systemd service file at $SERVICE_FILE..."

# Создание systemd service файла
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

# Перезагрузка systemd и запуск сервиса
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Starting StatusOpenVPN service..."
sudo systemctl start StatusOpenVPN
sudo systemctl enable StatusOpenVPN

# Получение внешнего IP-адреса сервера
EXTERNAL_IP=$(curl -s ifconfig.me)

echo "Running initial admin setup..."
ADMIN_PASS=$(python3 -c "from main import add_admin; print(add_admin())")


# Вывод информации о доступности сервера
echo "--------------------------------------------"
echo -e "\e[32mSetup completed successfully\e[0m"
echo "--------------------------------------------"
echo -e "Server is available at: \e[4;38;5;33mhttp://$EXTERNAL_IP:$PORT\e[0m"
echo -e "Admin password: \e[32m$ADMIN_PASS\e[0m"
echo "--------------------------------------------"


rm -f $TARGET_DIR/scripts/setup.sh $TARGET_DIR/README.md
