#!/bin/bash

echo "Activating virtual environment..."
source venv/bin/activate


echo "You are about to change the admin password. Please make sure you remember the new password."
read -p "Do you want to proceed? (Y/N): " confirm


if [[ "$confirm" =~ ^[Yy]$ ]]; then
    ADMIN_PASS=$(python3 -c "from main import change_admin_password; change_admin_password()")
    echo -e "Admin password successfully changed to: \e[32m$ADMIN_PASS\e[0m"
else
    echo "Password change canceled."
fi
