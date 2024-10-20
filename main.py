import csv
import sqlite3
import requests
import os
import random
import string
import subprocess
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask import Flask, render_template, url_for, flash, redirect, request

# from src import create_app
from src.forms import LoginForm
from src.config import Config
from flask_bcrypt import Bcrypt
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)

# app = create_app('DevelopmentConfig')


bcrypt = Bcrypt(app)
loginManager = LoginManager(app)
loginManager.login_view = "login"

# @loginManager.user_loader
# def load_user(user_id):
#     return User.query.get(int(user_id))


# Функция для подлючения к базе данных SQLite
def get_db_connection():
    conn = sqlite3.connect(app.config["DATABASE_PATH"])
    conn.row_factory = sqlite3.Row  # Для получения результатов в виде словаря
    return conn


# Создаем таблицу для пользователей (один раз при старте)
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


# Создание таблицы при запуске приложения
create_users_table()


# Flask-Login: Загрузка пользователей по его ID
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


# Класс пользователя для Flask-Login
class User(UserMixin):
    def __init__(self, user_id, username, role, password):
        self.id = user_id
        self.username = username
        self.role = role
        self.password = password


# Маршрут для логина
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    form = LoginForm()
    if form.validate_on_submit():
        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (form.username.data,)
        ).fetchone()
        conn.close()

        if user and bcrypt.check_password_hash(user["password"], form.password.data):
            user_obj = User(
                user_id=user["id"],
                username=user["username"],
                role=user["role"],
                password=user["password"],
            )
            login_user(user_obj)
            next_page = request.args.get("next")
            if not next_page == "/logout":
                return redirect(next_page or url_for("home"))
            else:
                return redirect(url_for("home"))
        else:
            flash("Неправильный логин или пароль!", "danger")
    return render_template("login.html", form=form)


# Маршрут для выхода из системы
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# Функция для добавления нового пользователя с зашифрованным паролем
def add_user(username, role, password):
    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO users (username, role, password) VALUES (?, ?, ?)",
        (username, role, hashed_password),
    )
    conn.commit()
    conn.close()


# Функция для получения данных WireGuard
def get_wireguard_stats():
    try:
        result = subprocess.run(
            ["/usr/bin/wg", "show"], capture_output=True, text=True, check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Команда wg show завершилась с ошибкой: {e.stderr}")
        return f"Ошибка выполнения команды: {e.stderr}"
    except FileNotFoundError:
        print(
            "Команда wg не найдена. Убедитесь, что WireGuard установлен и доступен в системе."
        )
        return "Команда wg не найдена."
    except Exception as e:
        print(f"Непредвиденная ошибка: {e}")
        return f"Непредвиденная ошибка: {e}"


# Функция для генерации случайного пароля
def get_random_pass(lenght=10):
    characters = string.ascii_letters + string.digits  # Буквы и цифры
    random_pass = "".join(random.choice(characters) for _ in range(lenght))
    return random_pass


# Добавление администратора при первом запуске
def add_admin():
    conn = get_db_connection()
    passw = get_random_pass()
    count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[
        0
    ]

    if count < 1:
        add_user("admin", "admin", passw)
        # print(f"Пароль администратора: {passw}")

    conn.close()
    return passw


# Функция для преобразования байт в удобный формат
def format_bytes(size):
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


# Функция для склонения слова "клиент"
def pluralize_clients(count):

    if 11 <= count % 100 <= 19:
        return f"{count} клиентов"
    elif count % 10 == 1:
        return f"{count} клиент"
    elif 2 <= count % 10 <= 4:
        return f"{count} клиента"
    else:
        return f"{count} клиентов"


# Функция для получения внешнего IP-адреса
def get_external_ip():
    try:
        # Отправляем запрос к сервису ipify, чтобы получить внешний IP
        response = requests.get("https://api.ipify.org", timeout=10)
        if response.status_code == 200:
            return response.text  # Возвращаем IP-адрес
        return "IP не найден"
    except requests.Timeout:
        return "Ошибка: запрос превысил время ожидания."
    except requests.ConnectionError:
        return "Ошибка: нет подключения к интернету."
    except requests.RequestException as e:
        return f"Ошибка при запросе: {e}"


# Преобразование даты
def format_date(date_string):
    date_obj = datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
    return date_obj.strftime("%d.%m.%Y [%H:%M]")


# Удаление префикса из имени клиента
def clean_client_name(name, prefix="antizapret-"):
    return name[len(prefix) :] if name.startswith(prefix) else name


# Маскируем IP-адрес
def mask_ip(ip_address):
    ip = ip_address.split(":")[0]
    parts = ip.split(".")
    if len(parts) == 4:
        # Добавляем ведущие нули, чтобы каждая часть занимала 3 символа
        parts = [f"{int(part):03}" for part in parts]

        return f"{parts[0]}.***.***.{parts[3]}"
    return ip_address


# Отсет времени
def format_duration(start_time):
    now = datetime.now()  # Текущее время
    delta = now - start_time  # Разница во времени

    days = delta.days
    seconds = delta.seconds
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if days >= 30:
        months = days // 30
        days %= 30
        return f"{months} мес. {days} дн. {hours} ч. {minutes} мин."
    elif days > 0:
        return f"{days} дн. {hours} ч. {minutes} мин."
    elif hours > 0:
        return f"{hours} ч. {minutes} мин."
    elif minutes > 0:
        return f"{minutes} мин."
    else:
        return f"{seconds} сек."


# Чтение данных из CSV и обработка
def read_csv(file_path, protocol):
    data = []
    total_received, total_sent = 0, 0
    try:
        with open(file_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # Пропускаем заголовок
            for row in reader:
                if row[0] == "CLIENT_LIST":
                    received, sent = int(row[5]), int(row[6])
                    total_received += received
                    total_sent += sent

                    start_date = datetime.strptime(row[7], "%Y-%m-%d %H:%M:%S")
                    duration = format_duration(start_date)

                    data.append(
                        [
                            clean_client_name(row[1]),
                            mask_ip(row[2]),
                            row[3],
                            format_bytes(received),
                            format_bytes(sent),
                            format_date(row[7]),
                            duration,
                            protocol,
                        ]
                    )
        return data, total_received, total_sent, None
    except FileNotFoundError:
        file_name = os.path.basename(file_path)
        file_directory = os.path.dirname(file_path)

        error_message = (
            f'Файл "{file_name}" не найден. '
            f"Пожалуйста, проверьте наличие файла по указанному пути: {file_directory}"
        )
        return [], 0, 0, error_message  # Возвращаем сообщение об ошибке


@app.errorhandler(404)
def page_not_found(_):
    return redirect(url_for("home"))


@app.route("/stats")
@login_required
def stats():
    return render_template("stats.html")


# @app.route("/wg")
# @login_required
# def wg():
#    wg_stats = get_wireguard_stats()
#    return render_template("wg.html", wg_stats=wg_stats)


@app.route("/")
@login_required
def home():

    udp_clients, udp_received, udp_sent, udp_error = read_csv(
        "/etc/openvpn/server/logs/antizapret-udp-status.log", "UDP"
    )
    tcp_clients, tcp_received, tcp_sent, tcp_error = read_csv(
        "/etc/openvpn/server/logs/antizapret-tcp-status.log", "TCP"
    )

    vpn_udp_clients, vpn_udp_received, vpn_udp_sent, vpn_udp_error = read_csv(
        "/etc/openvpn/server/logs/vpn-udp-status.log", "VPN-UDP"
    )
    vpn_tcp_clients, vpn_tcp_received, vpn_tcp_sent, vpn_tcp_error = read_csv(
        "/etc/openvpn/server/logs/vpn-tcp-status.log", "VPN-TCP"
    )

    if udp_error or tcp_error:
        error_message = udp_error or tcp_error
        return render_template("index.html", error_message=error_message)

    clients = udp_clients + tcp_clients + vpn_udp_clients + vpn_tcp_clients
    total_clients = len(clients)
    total_received = format_bytes(
        udp_received + tcp_received + vpn_udp_received + vpn_tcp_received
    )
    total_sent = format_bytes(udp_sent + tcp_sent + vpn_udp_sent + vpn_tcp_sent)
    server_ip = get_external_ip()

    return render_template(
        "index.html",
        clients=clients,
        total_clients_str=pluralize_clients(total_clients),
        total_received=total_received,
        total_sent=total_sent,
        server_ip=server_ip,
    )


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=1234)
