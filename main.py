import threading

from src.ui.extensions import app, bcrypt, loginManager
from src.ui.services.auth_service import (
    add_admin,
    change_admin_password,
    create_users_table,
)
from src.ui.services.system_info_service import (
    update_system_info,
    update_system_info_loop,
)

import src.ui.routes  # регистрирует Flask-маршруты на app


__all__ = [
    "app",
    "bcrypt",
    "loginManager",
    "add_admin",
    "change_admin_password",
    "create_users_table",
]


threading.Thread(target=update_system_info, daemon=True).start()
threading.Thread(target=update_system_info_loop, daemon=True).start()


if __name__ == "__main__":
    add_admin()
    app.run(debug=True, host="0.0.0.0", port=1234)
