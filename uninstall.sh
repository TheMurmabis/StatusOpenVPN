#Остановка и отключиение сервиса
sudo systemctl stop myapp
sudo systemctl disable myapp

#Удаление systemd unit файла
sudo rm /etc/systemd/system/myapp.service

#Перезагрузапусе systemd
sudo systemctl daemon-reload

#Удаление директории с проектом
sudo rm -rf /root/web
