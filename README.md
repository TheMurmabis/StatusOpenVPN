# Проект Flask с Gunicorn

## Описание

Этот проект представляет собой веб-приложение на Flask, которое показывает активные подключения OpenVPN.
Страница статистики доступна по адресу: IP-Adress:1234

## Установка и запуск

Для установки и запуска приложения в терминале под root выполнить
```bash
apt update && apt install -y git && git clone https://github.com/TheMurmabis/StatusOpenVPN.git web && chmod +x web/setup.sh && web/setup.sh
