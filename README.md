# Проект Flask с Gunicorn

## Описание

Этот проект представляет собой веб-приложение на Flask, которое показывает активные подключения OpenVPN.
Страница статистики доступна по адресу: IP-Address:1234

## Установка и запуск

Для установки и запуска приложения в терминале под root выполнить следующие команды:

### 1. Установка git
```bash
apt update && apt install -y git
```
### 2. Клонирование репозитория
```bash
git clone https://github.com/TheMurmabis/StatusOpenVPN.git web 
```
### 3. Запуск установки
```bash
chmod +x web/setup.sh && web/setup.sh
```
# Упрощенная команда

Для установки одной строкой выполнить команду:
```bash
apt update && apt install -y git && git clone https://github.com/TheMurmabis/StatusOpenVPN.git web && chmod +x web/setup.sh && web/setup.sh
```

