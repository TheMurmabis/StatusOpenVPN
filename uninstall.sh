#!/bin/bash

# Функция для вывода статуса с зелёной галочкой
success_status() {
  echo -e "\e[32m✔ $1\e[0m"
}

# Остановка и отключение сервиса
echo "Stopping and disabling the service"
if sudo systemctl stop myapp && sudo systemctl disable myapp; then
  success_status "Service stopped and disabled successfully"
else
  echo "Failed to stop and disable the service"
fi

# Удаление systemd unit файла
echo "Deleting the systemd unit file"
if sudo rm /etc/systemd/system/myapp.service; then
  success_status "Systemd unit file deleted successfully"
else
  echo "Failed to delete the systemd unit file"
fi

# Перезапуск systemd
echo "Restarting systemd"
if sudo systemctl daemon-reload; then
  success_status "Systemd reloaded successfully"
else
  echo "Failed to reload systemd"
fi

# Удаление директории с проектом
echo "Deleting a directory with a project"
if sudo rm -rf /root/web; then
  success_status "Directory deleted successfully"
else
  echo "Failed to delete the directory"
fi
