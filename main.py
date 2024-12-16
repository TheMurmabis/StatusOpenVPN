import csv
import sqlite3
import requests
import os
import re
import random
import time
import string
import psutil
import socket
import subprocess
from tzlocal import get_localzone
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask import (
    Flask,
    render_template,
    url_for,
    redirect,
    request,
    jsonify,
    session,
)
from src.forms import LoginForm
from src.config import Config
from flask_bcrypt import Bcrypt
from datetime import datetime, timezone, timedelta
from zoneinfo._common import ZoneInfoNotFoundError
from collections import defaultdict

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


# Вызываем функцию для создания таблицы при запуске приложения
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


# Функция для изменения пароля администратора
def change_admin_password():

    conn = get_db_connection()
    admin_user = conn.execute("SELECT * FROM users WHERE role = 'admin'").fetchone()

    if not admin_user:
        print("Администратор не найден.")
        conn.close()
        return

    passw = get_random_pass()  # Генерация нового пароля
    hashed_password = bcrypt.generate_password_hash(passw).decode("utf-8")

    conn.execute(
        "UPDATE users SET password = ? WHERE username = ? AND role = 'admin'",
        (hashed_password, "admin"),
    )
    conn.commit()
    conn.close()

    print(f"{passw}")


# ---------WireGuard----------
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


# Функция для получения данных WireGuard
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


# ---------OpenVPN----------
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
        response = requests.get("https://api.ipify.org", timeout=10)
        if response.status_code == 200:
            return response.text
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
    server_timezone = get_localzone()  # Получаем локальную временную зону сервера
    localized_date = date_obj.replace(
        tzinfo=server_timezone
    )  # Устанавливаем локальную временную зону
    utc_date = localized_date.astimezone(timezone.utc)  # Преобразуем в UTC

    return utc_date.isoformat()  # Возвращаем ISO формат


# Удаление префикса из имени клиента
def clean_client_name(name, prefix="antizapret-"):
    return name[len(prefix) :] if name.startswith(prefix) else name


# Маскируем IP-адрес
def mask_ip(ip_address):
    ip = ip_address.split(":")[0]
    parts = ip.split(".")
    if len(parts) == 4:
        # parts = [f"{int(part):03}" for part in parts] # Добавляем ведущие нули, если нужно
        parts = [str(int(part)) for part in parts]

        return f"{parts[0]}.{parts[1]}.{parts[2]}.{parts[3]}"
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


client_cache = defaultdict(lambda: {"received": 0, "sent": 0, "timestamp": None})


# Чтение данных из CSV и обработка
def read_csv(file_path, protocol):
    data = []
    total_received, total_sent = 0, 0
    current_time = datetime.now()

    if not os.path.exists(file_path):
        return [], 0, 0, None

    with open(file_path, newline="", encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile)
        next(reader)

        for row in reader:
            if row[0] == "CLIENT_LIST":
                client_name = row[1]
                received = int(row[5])
                sent = int(row[6])
                total_received += received
                total_sent += sent

                start_date = datetime.strptime(row[7], "%Y-%m-%d %H:%M:%S")
                duration = format_duration(start_date)

                # Получение предыдущих данных из кеша
                previous_data = client_cache.get(
                    client_name, {"received": 0, "sent": 0, "timestamp": None}
                )
                previous_received = previous_data["received"]
                previous_sent = previous_data["sent"]
                previous_time = previous_data["timestamp"]

                # Рассчитываем скорость
                if (
                    previous_time
                    and received >= previous_received
                    and sent >= previous_sent
                ):
                    time_diff = (current_time - previous_time).total_seconds()
                    if time_diff > 0:
                        download_speed = (received - previous_received) / time_diff
                        upload_speed = (sent - previous_sent) / time_diff
                    else:
                        download_speed = 0
                        upload_speed = 0
                else:
                    download_speed = 0
                    upload_speed = 0

                # Обновляем кеш
                client_cache[client_name] = {
                    "received": received,
                    "sent": sent,
                    "timestamp": current_time,
                }

                # Добавляем данные клиента
                data.append(
                    [
                        clean_client_name(client_name),
                        mask_ip(row[2]),
                        row[3],
                        format_bytes(received),
                        format_bytes(sent),
                        format_bytes(download_speed) + "/s",
                        format_bytes(upload_speed) + "/s",
                        format_date(row[7]),
                        duration,
                        protocol,
                    ]
                )

    return data, total_received, total_sent, None


# ---------Метрики----------
def get_network_load():
    net_io_start = psutil.net_io_counters(pernic=True)
    time.sleep(1)
    net_io_end = psutil.net_io_counters(pernic=True)

    network_data = {}
    for interface in net_io_start:
        sent_start, recv_start = (
            net_io_start[interface].bytes_sent,
            net_io_start[interface].bytes_recv,
        )
        sent_end, recv_end = (
            net_io_end[interface].bytes_sent,
            net_io_end[interface].bytes_recv,
        )

        sent_speed = (sent_end - sent_start) * 8 / 1e6
        recv_speed = (recv_end - recv_start) * 8 / 1e6

        # Сохраняем только интерфейсы с ненулевой загрузкой
        if sent_speed > 0 or recv_speed > 0:
            network_data[interface] = {
                "sent_speed": round(sent_speed, 2),
                "recv_speed": round(recv_speed, 2),
            }
    return network_data


def get_uptime():
    try:
        uptime = (
            subprocess.check_output("/usr/bin/uptime -p", shell=True).decode().strip()
        )
    except subprocess.CalledProcessError:
        uptime = "Не удалось получить время работы"
    return uptime


def format_uptime(uptime_string):
    # Регулярное выражение с учетом лет, месяцев, недель, дней, часов и минут
    pattern = r"(?:(\d+)\s*years?|(\d+)\s*months?|(\d+)\s*weeks?|(\d+)\s*days?|(\d+)\s*hours?|(\d+)\s*minutes?)"

    years = 0
    months = 0
    weeks = 0
    days = 0
    hours = 0
    minutes = 0

    matches = re.findall(pattern, uptime_string)

    for match in matches:
        if match[0]:  # Годы
            years = int(match[0])
        elif match[1]:  # Месяцы
            months = int(match[1])
        elif match[2]:  # Недели
            weeks = int(match[2])
        elif match[3]:  # Дни
            days = int(match[3])
        elif match[4]:  # Часы
            hours = int(match[4])
        elif match[5]:  # Минуты
            minutes = int(match[5])

    # Итоговая строка
    result = []
    if years > 0:
        result.append(f"{years} г.")
    if months > 0:
        result.append(f"{months} мес.")
    if weeks > 0:
        result.append(f"{weeks} нед.")
    if days > 0:
        result.append(f"{days} дн.")
    if hours > 0:
        result.append(f"{hours} ч.")
    if minutes > 0:
        result.append(f"{minutes} мин.")

    return " ".join(result)


# Переменная для хранения кэшированных данных
cached_system_info = None
last_fetch_time = 0
CACHE_DURATION = 10  # Время кэширования в секундах


def get_system_info():
    global last_fetch_time, cached_system_info

    current_time = time.time()
    if cached_system_info and (current_time - last_fetch_time < CACHE_DURATION):
        return cached_system_info

    system_info = {
        "cpu_load": psutil.cpu_percent(interval=1),
        "memory_used": psutil.virtual_memory().used // (1024**2),
        "memory_total": psutil.virtual_memory().total // (1024**2),
        "disk_used": psutil.disk_usage("/").used // (1024**3),
        "disk_total": psutil.disk_usage("/").total // (1024**3),
        "network_load": get_network_load(),
        "uptime": format_uptime(get_uptime()),
    }

    cached_system_info = system_info
    last_fetch_time = current_time
    return system_info


@app.errorhandler(404)
def page_not_found(_):
    return redirect(url_for("home"))


# Маршрут для выхода из системы
@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("login"))


@app.before_request
def track_last_activity():
    if current_user.is_authenticated:
        now = datetime.now(timezone.utc)
        last_activity = session.get("last_activity")

        if request.endpoint in ["login", "change_password", "update_profile"]:
            session["last_activity"] = now.isoformat()

        if last_activity:
            last_activity_time = datetime.fromisoformat(last_activity)
            if last_activity_time.tzinfo is None:
                last_activity_time = last_activity_time.replace(tzinfo=timezone.utc)
            elapsed_time = (now - last_activity_time).total_seconds()

            if elapsed_time > 300:  # 5 минут
                logout_user()
                session.clear()
                return redirect(url_for("login"))


# Маршрут для логина
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    form = LoginForm()
    error_message = None

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
            session.permanent = True
            app.permanent_session_lifetime = timedelta(minutes=5)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("home"))
        else:
            error_message = (
                "Неправильный логин или пароль!"  # Устанавливаем сообщение об ошибке
            )
    return render_template("login.html", form=form, error_message=error_message)


@app.route("/")
@login_required
def home():
    server_ip = get_external_ip()
    system_info = get_system_info()
    hostname = socket.gethostname()

    return render_template(
        "index.html",
        server_ip=server_ip,
        system_info=system_info,
        hostname=hostname,
        active_page="home",
    )


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
    try:
        # Пути к файлам и протоколы
        file_paths = [
            ("/etc/openvpn/server/logs/antizapret-udp-status.log", "UDP"),
            ("/etc/openvpn/server/logs/antizapret-tcp-status.log", "TCP"),
            ("/etc/openvpn/server/logs/vpn-udp-status.log", "VPN-UDP"),
            ("/etc/openvpn/server/logs/vpn-tcp-status.log", "VPN-TCP"),
            ("/etc/openvpn/server/logs/antizapret-no-cipher-status.log", "NoCipher"),
        ]

        clients = []
        total_received, total_sent = 0, 0
        errors = []

        # Проходим по всем файлам и обрабатываем их
        for file_path, protocol in file_paths:
            file_data, received, sent, error = read_csv(file_path, protocol)
            if error:
                errors.append(f"Ошибка в файле {file_path}: {error}")
            else:
                clients.extend(file_data)
                total_received += received
                total_sent += sent

        # # Проверка наличия файлов
        # if not clients:
        #     return render_template(
        #         "ovpn.html",
        #         error_message="Нет данных для отображения. Проверьте наличие файлов в /etc/openvpn/server/logs/",
        #         errors=errors,
        #         active_page="ovpn",
        #     )

        total_clients = len(clients)
        return render_template(
            "ovpn.html",
            clients=clients,
            total_clients_str=pluralize_clients(total_clients),
            total_received=format_bytes(total_received),
            total_sent=format_bytes(total_sent),
            active_page="ovpn",
            errors=errors,
        )

    except ZoneInfoNotFoundError:
        error_message = (
            "Обнаружены конфликтующие настройки часового пояса "
            "в файлах /etc/timezone и /etc/localtime. "
            "Попробуйте установить правильный часовой пояс "
            "с помощью команды: sudo dpkg-reconfigure tzdata"
        )
        return render_template("ovpn.html", error_message=error_message), 500

    except Exception as e:
        error_message = f"Произошла непредвиденная ошибка: {str(e)}"
        return render_template("ovpn.html", error_message=error_message), 500


if __name__ == "__main__":
    add_admin()
    app.run(debug=False, host="0.0.0.0", port=1234)
