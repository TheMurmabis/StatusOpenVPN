#!/bin/bash

# Обработка ошибок
set -e

# Переменные
REPO_URL="https://github.com/TheMurmabis/StatusOpenVPN.git"  # Замените на URL вашего репозитория
TARGET_DIR="/root/web"  # Папка, куда будет клонирован репозиторий

# Клонирование репозитория в папку web
echo "Cloning repository into $TARGET_DIR..."
git clone $REPO_URL $TARGET_DIR

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
SERVICE_FILE="/etc/systemd/system/myapp.service"
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
ExecStart=$TARGET_DIR/venv/bin/gunicorn -w 4 app:app -b 0.0.0.0:1234

[Install]
WantedBy=multi-user.target
EOF

# Перезагрузка systemd и запуск сервиса
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Starting myapp service..."
sudo systemctl start myapp

echo "Setup completed successfully!"
