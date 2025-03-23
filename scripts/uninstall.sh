#!/bin/bash

# Функция для вывода статуса с зелёной галочкой
success_status() {
  echo -e "\e[32m✔ $1\e[0m"
}

# Остановка и отключение сервиса
echo "Stopping and disabling the service"
if sudo systemctl stop StatusOpenVPN && sudo systemctl disable StatusOpenVPN; then
  success_status "Service stopped and disabled successfully"
else
  echo "Failed to stop and disable the service"
fi

# Остановка и отключение logs.service и logs.timer
echo "Stopping and disabling logs.service and logs.timer"
sudo systemctl stop logs.service logs.timer
sudo systemctl disable logs.service logs.timer

# Удаление systemd unit файла StatusOpenVPN
echo "Deleting the systemd unit file StatusOpenVPN.service"
if sudo rm /etc/systemd/system/StatusOpenVPN.service; then
  success_status "Systemd unit file deleted successfully"
else
  echo "Failed to delete the systemd unit file"
fi

# Удаление systemd unit файла telegram-bot
echo "Deleting the systemd unit file telegram-bot"
if sudo rm /etc/systemd/system/telegram-bot.service; then
  success_status "logs.timer deleted successfully"
else
  echo "Failed to delete logs.timer"
fi

# Удаление systemd unit файла logs.service
echo "Deleting the systemd unit file logs.service"
if sudo rm /etc/systemd/system/logs.service; then
  success_status "logs.service deleted successfully"
else
  echo "Failed to delete logs.service"
fi

# Удаление systemd unit файла logs.timer
echo "Deleting the systemd unit file logs.timer"
if sudo rm /etc/systemd/system/logs.timer; then
  success_status "logs.timer deleted successfully"
else
  echo "Failed to delete logs.timer"
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
