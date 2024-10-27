import csv
import sqlite3
import requests
import os
import re
import random
import string
import psutil
import subprocess
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask import Flask, render_template, url_for, flash, redirect, request, jsonify
from src.forms import LoginForm
from src.config import Config
from flask_bcrypt import Bcrypt
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)

bcrypt = Bcrypt(app)
loginManager = LoginManager(app)
loginManager.login_view = "login"


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


def change_admin_password():
    # Подключаемся к базе данных
    conn = get_db_connection()

    # Проверяем, есть ли администратор
    admin_user = conn.execute("SELECT * FROM users WHERE role = 'admin'").fetchone()

    if not admin_user:
        print("Администратор не найден.")
        conn.close()
        return
    # Генерируем новый пароль
    passw = get_random_pass()

    # Хешируем новый пароль
    hashed_password = bcrypt.generate_password_hash(passw).decode("utf-8")

    # Обновляем пароль в базе данных
    conn.execute(
        "UPDATE users SET password = ? WHERE username = ? AND role = 'admin'",
        (hashed_password, "admin"),
    )
    conn.commit()
    conn.close()

    print(f"Пароль администратора успешно изменен. Новый пароль: {passw}")


# -------WireGuard--------
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


def parse_wireguard_output(output):
    stats = []
    lines = output.strip().splitlines()
    interface_data = {}

    for line in lines:
        line = line.strip()
        if line.startswith("interface:"):
            if interface_data:
                stats.append(interface_data)
                interface_data = {}
            interface_data["interface"] = line.split(": ")[1]
        elif line.startswith("public key:"):
            interface_data["public_key"] = line.split(": ")[1]
        elif line.startswith("listening port:"):
            interface_data["listening_port"] = line.split(": ")[1]
        elif line.startswith("peer:"):
            if "peers" not in interface_data:
                interface_data["peers"] = []
            peer_data = {"peer": line.split(": ")[1].strip()}
            masked_peer = (
                peer_data["peer"][:4] + "..." + peer_data["peer"][-4:]
            )  # Маскируем peer: первые 4 и последние 4 символа

            peer_data["masked_peer"] = masked_peer
            interface_data["peers"].append(peer_data)
        elif line.startswith("preshared key:"):
            interface_data["peers"][-1]["preshared_key"] = line.split(": ")[1]
        elif line.startswith("endpoint:"):
            endpoint = line.split(": ")[1].strip()
            masked_endpoint = mask_ip(endpoint)
            interface_data["peers"][-1]["endpoint"] = masked_endpoint
        elif line.startswith("allowed ips:"):
            interface_data["peers"][-1]["allowed_ips"] = line.split(": ")[1]
        elif line.startswith("latest handshake:"):
            handshake_time = line.split(": ")[1].strip()
            formatted_handshake_time = format_handshake_time(handshake_time)
            interface_data["peers"][-1]["latest_handshake"] = formatted_handshake_time

        elif line.startswith("transfer:"):
            transfer_data = line.split(":")[1].strip().split(", ")
            received = transfer_data[0].replace(" received", "").strip()
            sent = transfer_data[1].replace(" sent", "").strip()
            interface_data["peers"][-1]["received"] = received
            interface_data["peers"][-1]["sent"] = sent

    if interface_data:
        stats.append(interface_data)

    return stats


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


def format_handshake_time(handshake_string):
    time_units = re.findall(r"(\d+)\s+(\w+)", handshake_string)

    # Словарь для перевода единиц времени в сокращения
    abbreviations = {
        "year": "г.",
        "years": "г.",
        "month": "мес.",
        "months": "мес.",
        "week": "нед.",
        "weeks": "нед.",
        "day": "дн.",
        "days": "дн.",
        "hour": "ч.",
        "hours": "ч.",
        "minute": "мин.",
        "minutes": "мин.",
        "second": "сек.",
        "seconds": "сек.",
    }

    # Формируем сокращенную строку
    formatted_time = " ".join(
        f"{value} {abbreviations[unit]}" for value, unit in time_units
    )

    return formatted_time


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


def get_system_info():
    return {
        "cpu_load": psutil.cpu_percent(interval=1),  # Нагрузка на ЦП (%)
        "memory_used": psutil.virtual_memory().used
        // (1024**2),  # Использование ОЗУ (в МБ)
        "memory_total": psutil.virtual_memory().total // (1024**2),  # Всего ОЗУ (в МБ)
        "disk_used": psutil.disk_usage("/").used
        // (1024**3),  # Использование диска (в ГБ)
        "disk_total": psutil.disk_usage("/").total
        // (1024**3),  # Всего места на диске (в ГБ)
    }


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


# Маршрут для выхода из системы
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


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


@app.route("/")
@login_required
def home():
    server_ip = get_external_ip()
    system_info = get_system_info()
    return render_template("index.html", server_ip=server_ip, system_info=system_info)


@app.route("/api/system_info")
@login_required
def api_system_info():
    system_info = get_system_info()
    return jsonify(system_info)


@app.route("/wg")
@login_required
def wg():
    stats = parse_wireguard_output(get_wireguard_stats())
    return render_template("wg.html", stats=stats, active_page="wg")


@app.route("/ovpn")
@login_required
def ovpn():

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
        return render_template("ovpn.html", error_message=error_message)

    clients = udp_clients + tcp_clients + vpn_udp_clients + vpn_tcp_clients
    total_clients = len(clients)
    total_received = format_bytes(
        udp_received + tcp_received + vpn_udp_received + vpn_tcp_received
    )
    total_sent = format_bytes(udp_sent + tcp_sent + vpn_udp_sent + vpn_tcp_sent)
    return render_template(
        "ovpn.html",
        clients=clients,
        total_clients_str=pluralize_clients(total_clients),
        total_received=total_received,
        total_sent=total_sent,
        active_page="ovpn",
    )


if __name__ == "__main__":
    add_admin()
    app.run(debug=True, host="0.0.0.0", port=1234)
