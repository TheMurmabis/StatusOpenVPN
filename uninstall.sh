#Остановка и отключение сервиса
echo "Stopping and disabling the service"
sudo systemctl stop myapp
sudo systemctl disable myapp

#Удаление systemd unit файла
echo "Deleting the systemd unit file"
sudo rm /etc/systemd/system/myapp.service

#Перезапуск systemd
echo "Restarting systemd"
sudo systemctl daemon-reload

#Удаление директории с проектом
echo "Deleting a directory with a project"
sudo rm -rf /root/web
