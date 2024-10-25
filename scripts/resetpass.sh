#!/bin/bash

# Путь к файлу db.db
DB_FILE="/root/web/src/db.db"

# Предупреждение о смене пароля
echo "Внимание: вы собираетесь сменить пароль администратора."
read -p "Вы уверены, что хотите продолжить? (y/n): " choice

if [[ "$choice" == "y" || "$choice" == "Y" ]]; then

    if [ -f "$DB_FILE" ]; then
        rm "$DB_FILE"
    else
        echo "Файл '$DB_FILE' не найден."
    fi

    # Перезапуск сервиса StatusOpenVPN
    sudo systemctl restart StatusOpenVPN
    echo "Сервис StatusOpenVPN был перезапущен."
else
    echo "Операция отменена."
fi
