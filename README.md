# Проект Flask с Gunicorn

## Описание

Этот проект представляет собой веб-приложение на Flask, которое запускается с помощью Gunicorn и настраивается для автоматического запуска с использованием systemd.

## Установка и запуск

Для установки и запуска приложения выполните следующие шаги:

### 1. В терминале под root выполнить
```bash
apt update && apt install -y git && git clone https://github.com/TheMurmabis/StatusOpenVPN.git web && chmod +x web/setup.sh && web/setup.sh
