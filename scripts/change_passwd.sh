#!/bin/bash

SERVICE="StatusOpenVPN"
UNIT_FILE="/etc/systemd/system/$SERVICE.service"
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")

echo "Activating virtual environment..."
source "$SCRIPT_DIR/../venv/bin/activate"

echo "You are about to change the admin password. Please make sure you remember the new password."
read -p "Do you want to proceed? (Y/N): " confirm

if [[ "$confirm" =~ ^[Yy]$ ]]; then
    ADMIN_PASS=$(PYTHONPATH="$SCRIPT_DIR/.." python3 -c "from main import change_admin_password; change_admin_password()")
    NEW_KEY=$(openssl rand -hex 32)

    sudo sed -i "s|Environment=\"SECRET_KEY=.*\"|Environment=\"SECRET_KEY=$NEW_KEY\"|" $UNIT_FILE
    sudo systemctl daemon-reload
    sudo systemctl restart $SERVICE

    echo -e "Admin password successfully changed to: \e[32m$ADMIN_PASS\e[0m"
else
    echo "Password change canceled."
fi
