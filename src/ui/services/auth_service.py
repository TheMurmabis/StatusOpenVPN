import random
import sqlite3
import string

from flask_login import UserMixin

from src.ui.extensions import app, bcrypt, loginManager


class User(UserMixin):
    def __init__(self, user_id, username, role, password):
        self.id = user_id
        self.username = username
        self.role = role
        self.password = password


def get_db_connection():
    conn = sqlite3.connect(app.config["DATABASE_PATH"])
    conn.row_factory = sqlite3.Row
    return conn


def create_users_table():
    conn = get_db_connection()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            role  TEXT NOT NULL,
            password TEXT NOT NULL
        )
    """
    )
    conn.commit()
    conn.close()


@loginManager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if user:
        return User(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            password=user["password"],
        )
    return None


def add_user(username, role, password):
    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO users (username, role, password) VALUES (?, ?, ?)",
        (username, role, hashed_password),
    )
    conn.commit()
    conn.close()


def get_random_pass(lenght=10):
    characters = string.ascii_letters + string.digits
    random_pass = "".join(random.choice(characters) for _ in range(lenght))
    return random_pass


def add_admin():
    conn = get_db_connection()
    passw = get_random_pass()
    count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[
        0
    ]

    if count < 1:
        add_user("admin", "admin", passw)

    conn.close()
    return passw


def change_admin_password():
    conn = get_db_connection()
    admin_user = conn.execute("SELECT * FROM users WHERE role = 'admin'").fetchone()

    if not admin_user:
        print("Администратор не найден.")
        conn.close()
        return

    passw = get_random_pass()
    hashed_password = bcrypt.generate_password_hash(passw).decode("utf-8")

    conn.execute(
        "UPDATE users SET password = ? WHERE username = ? AND role = 'admin'",
        (hashed_password, "admin"),
    )
    conn.commit()
    conn.close()

    print(f"{passw}")


create_users_table()
