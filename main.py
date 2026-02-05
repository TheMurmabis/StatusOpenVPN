import csv
import sqlite3
import requests
import os
import re
import threading
import random
import time
import string
import psutil
import socket
import subprocess
import json

from statistics import mean
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
    make_response,
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
from datetime import date, datetime, timezone, timedelta
from zoneinfo._common import ZoneInfoNotFoundError
from collections import defaultdict


class ScriptNameMiddleware:

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Получаем префикс из заголовка X-Script-Name
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        
        # Если заголовок присутствует, устанавливаем SCRIPT_NAME
        if script_name:
            # Убираем завершающий слэш, если есть
            script_name = script_name.rstrip('/')
            environ['SCRIPT_NAME'] = script_name
            
            # Корректируем PATH_INFO, убирая префикс (если Nginx его не удалил)
            # Это нужно на случай, если proxy_pass настроен без завершающего слэша
            path_info = environ.get('PATH_INFO', '')
            if path_info.startswith(script_name):
                new_path = path_info[len(script_name):]
                environ['PATH_INFO'] = new_path if new_path else '/'
        
        return self.app(environ, start_response)


app = Flask(__name__)
app.config.from_object(Config)

# Применяем middleware для обработки префикса пути
app.wsgi_app = ScriptNameMiddleware(app.wsgi_app)

bcrypt = Bcrypt(app)
loginManager = LoginManager(app)
loginManager.login_view = "login"

# Переменная для хранения кэшированных данных
cached_system_info = None
last_fetch_time = 0
CACHE_DURATION = 10  # обновление кэша каждые 10 секунд
cpu_history = []
ram_history = []
MAX_CPU_HISTORY = 60 * 12  # хранить 12 часов с шагом 1 минута
DB_SAVE_INTERVAL = 300  # запись в БД каждые 5 минут
last_db_save = 0

SAMPLE_INTERVAL = 10  # текущая частота сбора
MAX_HISTORY_SECONDS = 7 * 24 * 3600  # сколько секунд хранить в памяти
LIVE_POINTS = 60
last_collect = 0


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


def is_peer_online(last_handshake):
    if not last_handshake:
        return False
    return datetime.now() - last_handshake < timedelta(minutes=3)


def parse_relative_time(relative_time):
    """Преобразует строку с днями, часами, минутами и секундами в абсолютное время."""
    now = datetime.now()
    time_deltas = {"days": 0, "hours": 0, "minutes": 0, "seconds": 0}

    # Разбиваем строку на части
    parts = relative_time.split()
    i = 0
    while i < len(parts):
        try:
            value = int(parts[i])  # Извлекаем число
            unit = parts[i + 1]  # Следующее слово — это единица времени
            if "д" in unit or "day" in unit:
                time_deltas["days"] += value
            elif "ч" in unit or "hour" in unit:
                time_deltas["hours"] += value
            elif "мин" in unit or "minute" in unit:
                time_deltas["minutes"] += value
            elif "сек" in unit or "second" in unit:
                time_deltas["seconds"] += value
            i += 2  # Пропускаем число и единицу времени
        except (ValueError, IndexError):
            break  # Если данные некорректны, прерываем

    # Вычисляем итоговую разницу времени
    delta = timedelta(
        days=time_deltas["days"],
        hours=time_deltas["hours"],
        minutes=time_deltas["minutes"],
        seconds=time_deltas["seconds"],
    )

    return now - delta


def read_wg_config(file_path):
    """Считывает клиентские данные из конфигурационного файла WireGuard."""
    client_mapping = {}

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            current_client_name = None

            for line in file:
                line = line.strip()

                # Если строка начинается с # Client =, то сохраняем имя клиента
                if line.startswith("# Client ="):
                    current_client_name = line.split("=", 1)[1].strip()

                # Если строка начинается с [Peer], сбрасываем имя клиента
                elif line.startswith("[Peer]"):
                    # Проверяем, есть ли имя клиента, если нет, то оставляем 'N/A'
                    current_client_name = current_client_name or "N/A"

                # Если строка начинается с PublicKey =, сохраняем публичный ключ с именем клиента
                elif line.startswith("PublicKey =") and current_client_name:
                    public_key = line.split("=", 1)[1].strip()
                    client_mapping[public_key] = current_client_name

    except FileNotFoundError:
        print(f"Конфигурационный файл {file_path} не найден.")

    # print(client_mapping)
    return client_mapping


def get_daily_stats_map():
    """Получение ежедневной статистики WG"""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(app.config["WG_STATS_PATH"])
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM wg_daily_stats WHERE date = ?", (today,))
    rows = cursor.fetchall()
    conn.close()
    return {(row["peer"], row["interface"]): row for row in rows}


def humanize_bytes(num, suffix="B"):
    """Функция для преобразования байт в удобный формат"""
    for unit in ["", "K", "M", "G", "T"]:
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f} P{suffix}"


def parse_wireguard_output(output):
    """Парсинг вывода команды wg show."""
    stats = []
    lines = output.strip().splitlines()
    interface_data = {}

    vpn_mapping = read_wg_config("/etc/wireguard/vpn.conf")
    antizapret_mapping = read_wg_config("/etc/wireguard/antizapret.conf")
    client_mapping = {**vpn_mapping, **antizapret_mapping}
    daily_stats_map = get_daily_stats_map()

    for line in lines:
        line = line.strip()
        if line.startswith("interface:"):
            if interface_data:
                stats.append(interface_data)
                interface_data = {}
            interface_data["interface"] = line.split(": ")[1]
        elif line.startswith("public key:"):
            public_key = line.split(": ")[1]
            interface_data["public_key"] = public_key
        elif line.startswith("listening port:"):
            interface_data["listening_port"] = line.split(": ")[1]
        elif line.startswith("peer:"):
            if "peers" not in interface_data:
                interface_data["peers"] = []
            peer_data = {"peer": line.split(": ")[1].strip()}
            masked_peer = peer_data["peer"][:4] + "..." + peer_data["peer"][-4:]
            peer_data["masked_peer"] = masked_peer
            peer_data["client"] = client_mapping.get(peer_data["peer"], "N/A")

            daily_row = daily_stats_map.get(
                (peer_data["peer"], interface_data["interface"])
            )
            if daily_row:
                peer_data["daily_received"] = humanize_bytes(daily_row["received"])
                peer_data["daily_sent"] = humanize_bytes(daily_row["sent"])
                try:
                    total = parse_bytes(peer_data["received"]) + parse_bytes(
                        peer_data["sent"]
                    )
                    daily_total = daily_row["received"] + daily_row["sent"]
                    round_res = round((daily_total / total * 100) if total > 0 else 0)
                    peer_data["daily_traffic_percentage"] = round_res
                except Exception:
                    peer_data["daily_traffic_percentage"] = 0
            else:
                peer_data["daily_received"] = "0 B"
                peer_data["daily_sent"] = "0 B"
                peer_data["daily_traffic_percentage"] = 0
            interface_data["peers"].append(peer_data)
        elif line.startswith("endpoint:"):
            peer_data["endpoint"] = mask_ip(line.split(": ")[1].strip())
        elif line.startswith("allowed ips:"):
            allowed_ips = line.split(": ")[1].split(", ")
            peer_data["allowed_ips"] = allowed_ips
            peer_data["visible_ips"] = allowed_ips[:1]
            peer_data["hidden_ips"] = allowed_ips[1:]
        elif line.startswith("latest handshake:"):
            handshake_time = line.split(": ")[1].strip()

            if handshake_time.lower() == "now":
                formatted_handshake_time = datetime.now()
                peer_data["latest_handshake"] = "Now"
                peer_data["online"] = True

            elif any(
                unit in handshake_time
                for unit in ["мин", "час", "сек", "minute", "hour", "second", "day", "week"]
            ):
                formatted_handshake_time = parse_relative_time(handshake_time)
                peer_data["latest_handshake"] = format_handshake_time(handshake_time)
                peer_data["online"] = is_peer_online(formatted_handshake_time)

            else:
                formatted_handshake_time = datetime.strptime(
                    handshake_time, "%Y-%m-%d %H:%M:%S"
                )
                peer_data["latest_handshake"] = format_handshake_time(handshake_time)
                peer_data["online"] = is_peer_online(formatted_handshake_time)
        
        elif line.startswith("latest handshake:"):
            handshake_time = line.split(": ")[1].strip()
            if any(
                unit in handshake_time
                for unit in ["мин", "час", "сек", "minute", "hour", "second"]
            ):
                formatted_handshake_time = parse_relative_time(handshake_time)
            else:
                formatted_handshake_time = datetime.strptime(
                    handshake_time, "%Y-%m-%d %H:%M:%S"
                )
            peer_data["latest_handshake"] = format_handshake_time(handshake_time)
            peer_data["online"] = is_peer_online(formatted_handshake_time)
        elif line.startswith("transfer:"):
            transfer_data = line.split(":")[1].strip().split(", ")
            received = transfer_data[0].replace(" received", "").strip()
            sent = transfer_data[1].replace(" sent", "").strip()

            received_str = transfer_data[0].replace(" received", "").strip()
            sent_str = transfer_data[1].replace(" sent", "").strip()

            # Конвертируем строки в байты
            peer_data["received_bytes"] = (
                parse_bytes(received_str) if received_str else 0
            )
            peer_data["sent_bytes"] = parse_bytes(sent_str) if sent_str else 0

            peer_data["received"] = received if received else "0 B"
            peer_data["sent"] = sent if sent else "0 B"

            total_bytes = peer_data["received_bytes"] + peer_data["sent_bytes"]
            peer_data["received_percentage"] = (
                round((peer_data["received_bytes"] / total_bytes * 100), 2)
                if total_bytes > 0
                else 0
            )
            peer_data["sent_percentage"] = (
                round((peer_data["sent_bytes"] / total_bytes * 100), 2)
                if total_bytes > 0
                else 0
            )

    if interface_data:
        stats.append(interface_data)

    return stats


def get_daily_stats():
    """Получение ежедневной статистики"""
    conn = sqlite3.connect(app.config["WG_STATS_PATH"])
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    date_today = date.today().isoformat()

    cursor.execute(
        "SELECT interface, client, received, sent FROM wg_daily_stats WHERE date = ?",
        (date_today,),
    )
    rows = cursor.fetchall()
    conn.close()

    stats = {}
    for row in rows:
        iface = row["interface"]
        client = row["client"]
        if iface not in stats:
            stats[iface] = {}
        stats[iface][client] = {"received": row["received"], "sent": row["sent"]}

    return stats


# ---------OpenVPN----------
# Функция для преобразования байт в удобный формат
def format_bytes(size):
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def parse_bytes(value):
    """Преобразует строку с размером данных в байты."""
    size, unit = value.split(" ")
    size = float(size)
    unit = unit.lower()
    if unit == "kb":
        return size * 1024
    elif unit == "mb":
        return size * 1024**2
    elif unit == "gb":
        return size * 1024**3
    elif unit == "tb":
        return size * 1024**4
    return size


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
    server_timezone = get_localzone()
    localized_date = date_obj.replace(tzinfo=server_timezone)
    utc_date = localized_date.astimezone(timezone.utc)
    return utc_date.isoformat()


# Маскируем IP-адрес
def mask_ip(ip_address):
    if not ip_address:
        return "0.0.0.0"  # Значение по умолчанию

    ip = ip_address.split(":")[0]
    parts = ip.split(".")

    if len(parts) == 4:
        try:
            parts = [str(int(part)) for part in parts]
            return f"{parts[0]}.{parts[1]}.{parts[2]}.{parts[3]}"
        except ValueError:
            return ip

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

                # Получение предыдущих данных из кэша
                previous_data = client_cache.get(
                    client_name, {"received": 0, "sent": 0, "timestamp": current_time}
                )
                previous_received = previous_data["received"]
                previous_sent = previous_data["sent"]
                previous_time = previous_data["timestamp"]

                # Рассчитываем скорость только при валидной разнице времени
                time_diff = (current_time - previous_time).total_seconds()
                if time_diff >= 30:  # Учитываем фиксированный интервал обновления логов
                    download_speed = (
                        (received - previous_received) / time_diff
                        if received >= previous_received
                        else 0
                    )
                    upload_speed = (
                        (sent - previous_sent) / time_diff
                        if sent >= previous_sent
                        else 0
                    )
                else:
                    download_speed = 0
                    upload_speed = 0

                # Обновляем кэш
                client_cache[client_name] = {
                    "received": received,
                    "sent": sent,
                    "timestamp": current_time,
                }

                # Добавляем данные клиента
                data.append(
                    [
                        client_name,
                        mask_ip(row[2]),
                        row[3],
                        format_bytes(received),
                        format_bytes(sent),
                        f"{format_bytes(max(download_speed, 0))}/s",
                        f"{format_bytes(max(upload_speed, 0))}/s",
                        format_date(row[7]),
                        duration,
                        protocol,
                    ]
                )

    return data, total_received, total_sent, None


# ---------Метрики----------
def ensure_db():
    """Создает таблицу system_stats, если она не существует."""

    conn = sqlite3.connect(app.config["SYSTEM_STATS_PATH"])
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS system_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            cpu_percent REAL,
            ram_percent REAL
        )
    """
    )

    conn.commit()
    conn.close()


def save_minute_average_to_db():
    """Сохраняет средние значения CPU и RAM за последний интервал в БД."""
    now = datetime.now()
    cutoff = now - timedelta(seconds=DB_SAVE_INTERVAL)
    to_avg = [p for p in cpu_history if p["timestamp"] >= cutoff]
    if not to_avg:
        return
    cpu_avg = mean([p["cpu"] for p in to_avg])
    ram_avg = mean([p["ram"] for p in to_avg])

    try:
        conn = sqlite3.connect(app.config["SYSTEM_STATS_PATH"])
        cur = conn.cursor()
        # записываем timestamp = now (local)
        cur.execute(
            "INSERT INTO system_stats (timestamp, cpu_percent, ram_percent) VALUES (?, ?, ?)",
            (now.strftime("%Y-%m-%d %H:%M:%S"), round(cpu_avg, 3), round(ram_avg, 3)),
        )

        # Очищаем старые записи старше 7 дней
        cutoff_db = now - timedelta(days=7)
        cur.execute(
            "DELETE FROM system_stats WHERE timestamp < ?",
            (cutoff_db.strftime("%Y-%m-%d %H:%M:%S"),),
        )

        conn.commit()
        conn.close()
    except Exception as e:
        print("[DB ERROR] save_minute_average_to_db:", e)


def group_rows(rows, interval="minute"):
    """Группирует ряды по интервалу и усредняет значения CPU и RAM."""

    grouped = {}

    for r in rows:
        ts = r["timestamp"]

        if interval == "minute":
            key = ts.replace(second=0, microsecond=0)

        elif interval == "hour":
            key = ts.replace(minute=0, second=0, microsecond=0)

        elif interval == "day":
            key = ts.replace(hour=0, minute=0, second=0, microsecond=0)

        else:
            key = ts

        if key not in grouped:
            grouped[key] = {"cpu": [], "ram": []}

        grouped[key]["cpu"].append(r["cpu"])
        grouped[key]["ram"].append(r["ram"])

    # Усреднение
    result = []
    for key, values in grouped.items():
        result.append(
            {
                "timestamp": key,
                "cpu": sum(values["cpu"]) / len(values["cpu"]),
                "ram": sum(values["ram"]) / len(values["ram"]),
            }
        )

    return sorted(result, key=lambda x: x["timestamp"])


def resample_to_n(data, n):
    """Возвращает ровно n точек (если меньше — возвращает всё). Берёт равномерно распределённые индексы."""
    if not data:
        return []
    if len(data) <= n:
        return data
    step = len(data) / n
    out = []
    for i in range(n):
        idx = int(i * step)
        if idx >= len(data):
            idx = len(data) - 1
        out.append(data[idx])
    return out


def update_system_info_loop():
    global last_db_save, last_collect
    ensure_db()

    while True:
        now = time.time()
        if now - last_collect >= SAMPLE_INTERVAL:
            # psutil: non-blocking
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            ts = datetime.now()
            cpu_history.append({"timestamp": ts, "cpu": cpu, "ram": ram})
            # trim by time (keep at most MAX_HISTORY_SECONDS seconds)
            cutoff = datetime.now() - timedelta(seconds=MAX_HISTORY_SECONDS)
            # remove from start while older than cutoff
            while cpu_history and cpu_history[0]["timestamp"] < cutoff:
                cpu_history.pop(0)
            last_collect = now

        # сохранить среднее в БД каждые DB_SAVE_INTERVAL
        if now - last_db_save >= DB_SAVE_INTERVAL:
            save_minute_average_to_db()
            last_db_save = now

        time.sleep(1)


def get_default_interface():
    try:
        result = subprocess.run(
            ["/usr/bin/ip", "route"], capture_output=True, text=True, check=True
        )
        for line in result.stdout.splitlines():
            if "default" in line:
                return line.split()[4]
    except Exception as e:
        print(f"Ошибка: {e}")
    return None


def get_network_stats(interface):
    try:
        with open(
            f"/sys/class/net/{interface}/statistics/rx_bytes", "r", encoding="utf-8"
        ) as f:
            rx_bytes = int(f.read().strip())
        with open(
            f"/sys/class/net/{interface}/statistics/tx_bytes", "r", encoding="utf-8"
        ) as f:
            tx_bytes = int(f.read().strip())
        return {"interface": interface, "rx": rx_bytes, "tx": tx_bytes}
    except FileNotFoundError:
        return None  # Если интерфейс не найден


def get_network_load():
    net_io_start = psutil.net_io_counters(pernic=True)
    time.sleep(1)
    net_io_end = psutil.net_io_counters(pernic=True)

    network_data = {}
    for interface in net_io_start:
        if interface == "lo":
            continue

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


def count_online_clients(file_paths):
    total_openvpn = 0
    results = {}

    # Подсчёт WireGuard
    try:
        wg_output = subprocess.check_output(["/usr/bin/wg", "show"], text=True)
        wg_latest_handshakes = re.findall(r"latest handshake: (.+)", wg_output)

        online_wg = 0
        for handshake in wg_latest_handshakes:
            handshake_str = handshake.strip()
            if handshake_str == "0 seconds ago":
                online_wg += 1
            else:
                try:
                    # Используем parse_relative_time и is_peer_online для определения онлайн-статуса
                    handshake_time = parse_relative_time(handshake_str)
                    if is_peer_online(handshake_time):
                        online_wg += 1
                except Exception:
                    continue
        results["WireGuard"] = online_wg
    except Exception:
        results["WireGuard"] = 0  # или f"Ошибка: {e}" по желанию

    # Подсчёт OpenVPN
    for path, _ in file_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("CLIENT_LIST"):
                        total_openvpn += 1
        except:
            continue

    results["OpenVPN"] = total_openvpn
    return results


def get_system_info():
    global cached_system_info
    return cached_system_info


def update_system_info():
    global cached_system_info, last_fetch_time, cpu_history, last_db_save

    file_paths = [
        ("/etc/openvpn/server/logs/antizapret-udp-status.log", "UDP"),
        ("/etc/openvpn/server/logs/antizapret-tcp-status.log", "TCP"),
        ("/etc/openvpn/server/logs/vpn-udp-status.log", "VPN-UDP"),
        ("/etc/openvpn/server/logs/vpn-tcp-status.log", "VPN-TCP"),
    ]

    while True:
        current_time = time.time()
        if not cached_system_info or (current_time - last_fetch_time >= CACHE_DURATION):
            cpu_percent = psutil.cpu_percent(interval=1)
            ram_percent = psutil.virtual_memory().percent
            timestamp = datetime.now()

            # Обновление live истории в памяти
            cpu_history.append(
                {"timestamp": timestamp, "cpu": cpu_percent, "ram": ram_percent}
            )
            if len(cpu_history) > MAX_CPU_HISTORY:
                cpu_history.pop(0)  # удаляем старые записи

            interface = get_default_interface()
            network_stats = get_network_stats(interface) if interface else None
            vpn_clients = count_online_clients(file_paths)

            cached_system_info = {
                "cpu_load": cpu_percent,
                "memory_used": psutil.virtual_memory().used // (1024**2),
                "memory_total": psutil.virtual_memory().total // (1024**2),
                "disk_used": psutil.disk_usage("/").used // (1024**3),
                "disk_total": psutil.disk_usage("/").total // (1024**3),
                "network_load": get_network_load(),
                "uptime": format_uptime(get_uptime()),
                "network_interface": interface or "Не найдено",
                "rx_bytes": format_bytes(network_stats["rx"]) if network_stats else 0,
                "tx_bytes": format_bytes(network_stats["tx"]) if network_stats else 0,
                "vpn_clients": vpn_clients,
            }

            last_fetch_time = current_time

        time.sleep(CACHE_DURATION)


# Запуск фоновой задачи
threading.Thread(target=update_system_info, daemon=True).start()
threading.Thread(target=update_system_info_loop, daemon=True).start()


def get_vnstat_interfaces():
    try:
        result = subprocess.run(
            ["/usr/bin/vnstat", "--json"], capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)

        interfaces = []
        for iface in data.get("interfaces", []):
            name = iface.get("name")
            traffic = iface.get("traffic", {}).get("total", {})
            rx = traffic.get("rx", 0)
            tx = traffic.get("tx", 0)

            # Добавляем только если есть трафик
            if (rx + tx) > 0:
                interfaces.append(name)

        return interfaces

    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Ошибка при получении интерфейсов: {e}")
        return []


# @app.errorhandler(404)
# def page_not_found(_):
#     return redirect(url_for("home"))


# Маршрут для выхода из системы
@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    session.pop("last_activity", None)
    return redirect(url_for("login"))


@app.before_request
def track_last_activity():
    if request.path.startswith("/api/"):
        return

    session.permanent = True
    session["last_activity"] = time.time()


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
            login_user(user_obj, remember=form.remember_me.data)

            # Просто указываем, должна ли сессия быть "долгой"
            session.permanent = form.remember_me.data

            next_page = request.args.get("next")
            return redirect(next_page or url_for("home"))
        else:
            error_message = "Неправильный логин или пароль!"

    # Добавляем заголовок запрета индексации
    resp = make_response(
        render_template("login.html", form=form, error_message=error_message)
    )
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


def get_git_version():
    try:
        version = (
            subprocess.check_output(
                ["/usr/bin/git", "describe", "--tags", "--abbrev=0"],
                stderr=subprocess.DEVNULL,
            )
            .strip()
            .decode()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        version = "unknown"
    return version


@app.context_processor
def inject_info():
    return {
        "hostname": socket.gethostname(),
        "server_ip": get_external_ip(),
        "version": get_git_version(),
        "base_path": request.script_root or "",
    }


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
    """Маршрут клиентов WireGuard"""
    stats = parse_wireguard_output(get_wireguard_stats())

    return render_template("wg.html", stats=stats, active_page="wg")


@app.route("/api/wg/stats")
@login_required
def api_wg_stats():
    try:
        stats = parse_wireguard_output(get_wireguard_stats())
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
        ]

        clients = []
        total_received, total_sent = 0, 0
        errors = []

        for file_path, protocol in file_paths:
            file_data, received, sent, error = read_csv(file_path, protocol)
            if error:
                errors.append(f"Ошибка в файле {file_path}: {error}")
            else:
                clients.extend(file_data)
                total_received += received
                total_sent += sent

        # Сортировка данных
        sort_by = request.args.get("sort", "client")
        order = request.args.get("order", "asc")
        reverse_order = order == "desc"

        if sort_by == "client":
            clients.sort(key=lambda x: x[0], reverse=reverse_order)
        elif sort_by == "realIp":
            clients.sort(key=lambda x: x[1], reverse=reverse_order)
        elif sort_by == "localIp":
            clients.sort(key=lambda x: x[2], reverse=reverse_order)
        elif sort_by == "sent":
            clients.sort(key=lambda x: parse_bytes(x[3]), reverse=reverse_order)
        elif sort_by == "received":
            clients.sort(key=lambda x: parse_bytes(x[4]), reverse=reverse_order)
        elif sort_by == "connection-time":
            clients.sort(key=lambda x: x[7], reverse=reverse_order)
        elif sort_by == "duration":
            clients.sort(key=lambda x: x[7], reverse=reverse_order)
        elif sort_by == "protocol":
            clients.sort(key=lambda x: x[9], reverse=reverse_order)

        total_clients = len(clients)
        return render_template(
            "ovpn.html",
            clients=clients,
            total_clients_str=pluralize_clients(total_clients),
            total_received=format_bytes(total_received),
            total_sent=format_bytes(total_sent),
            active_section="ovpn",
            active_page="clients",
            errors=errors,
            sort_by=sort_by,
            order=order,
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


@app.route("/ovpn/history")
@login_required
def ovpn_history():
    try:
        logs = []
        conn_logs = sqlite3.connect(app.config["LOGS_DATABASE_PATH"])
        logs_reader = conn_logs.execute("SELECT * from connection_logs").fetchall()
        conn_logs.close()

        logs = sorted(
            [
                {
                    "client_name": row[1],
                    "real_ip": mask_ip(row[3]),
                    "local_ip": row[2],
                    "connection_since": row[4],
                    "protocol": row[7],
                }
                for row in logs_reader
            ],
            key=lambda x: x["connection_since"],
            reverse=True,  # Сортировка по убыванию
        )

        return render_template(
            "ovpn_history.html",
            active_section="ovpn",
            active_page="history",
            logs=logs,
        )

    except Exception as e:
        error_message = f"Произошла непредвиденная ошибка: {str(e)}"
        return render_template("ovpn_history.html", error_message=error_message), 500


@app.route("/ovpn/stats")
@login_required
def ovpn_stats():
    try:
        sort_by = request.args.get("sort", "client_name")
        order = request.args.get("order", "asc").lower()

        # Разрешённые поля сортировки (ключ -> SQL)
        allowed_sorts = {
            "client_name": "client_name",
            "total_bytes_sent": "SUM(total_bytes_received)",
            "total_bytes_received": "SUM(total_bytes_sent)",
            "last_connected": "MAX(last_connected)",
        }

        # Если параметр некорректный — сбрасываем на client_name
        sort_column = allowed_sorts.get(sort_by, "client_name")
        order = "DESC" if order == "desc" else "ASC"

        current_month = datetime.now().strftime("%b. %Y")
        previous_month_date = datetime.now().replace(day=1) - timedelta(days=1)
        previous_month = previous_month_date.strftime("%b. %Y")

        month_stats = {}
        total_received, total_sent = 0, 0

        with sqlite3.connect(app.config["LOGS_DATABASE_PATH"]) as conn:
            for month in [current_month, previous_month]:
                query = f"""
                    SELECT client_name,
                           SUM(total_bytes_sent),
                           SUM(total_bytes_received),
                           MAX(last_connected)
                    FROM monthly_stats
                    WHERE month = ?
                    GROUP BY client_name
                    ORDER BY {sort_column} {order}
                """
                rows = conn.execute(query, (month,)).fetchall()

                if rows:
                    stats_list = []
                    for client_name, sent, received, last_connected in rows:
                        total_received += received or 0
                        total_sent += sent or 0
                        stats_list.append(
                            {
                                "client_name": client_name,
                                "total_bytes_sent": format_bytes(received),
                                "total_bytes_received": format_bytes(sent),
                                "last_connected": last_connected,
                            }
                        )
                    month_stats[month] = stats_list

        return render_template(
            "ovpn_stats.html",
            total_received=format_bytes(total_received),
            total_sent=format_bytes(total_sent),
            active_section="ovpn",
            active_page="stats",
            month_stats=month_stats,
            current_month=current_month,
            previous_month=previous_month if previous_month in month_stats else None,
            sort_by=sort_by,
            order=order.lower(),
        )

    except Exception as e:
        error_message = f"Произошла непредвиденная ошибка: {e}"
        return render_template("ovpn_stats.html", error_message=error_message), 500


@app.route("/api/bw")
@login_required
def api_bw():
    q_iface = request.args.get("iface")
    period = request.args.get("period", "day")
    vnstat_bin = os.environ.get("VNSTAT_BIN", "/usr/bin/vnstat")

    # Получаем список интерфейсов
    try:
        proc = subprocess.run(
            [vnstat_bin, "--json"], check=True, capture_output=True, text=True
        )
        data = json.loads(proc.stdout)
        interfaces = [iface["name"] for iface in data.get("interfaces", [])]
    except subprocess.CalledProcessError:
        interfaces = []
    except json.JSONDecodeError:
        interfaces = []

    if not interfaces:
        return jsonify({"error": "Нет интерфейсов vnstat", "iface": None}), 500

    iface = q_iface if q_iface in interfaces else interfaces[0]

    # Настройка периодов
    if period == "hour":
        vnstat_option = "f"  # каждые 5 минут
        points = 12
        interval_seconds = 300
    elif period == "day":
        vnstat_option = "h"  # по часам
        points = 24
        interval_seconds = 3600
    elif period == "week":
        vnstat_option = "d"
        points = 7
        interval_seconds = 86400
    elif period == "month":
        vnstat_option = "d"
        points = 30
        interval_seconds = 86400
    else:
        vnstat_option = "h"
        points = 24
        interval_seconds = 3600

    # Получаем JSON от vnstat
    try:
        proc = subprocess.run(
            [vnstat_bin, "--json", vnstat_option, "-i", iface],
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(proc.stdout)
    except subprocess.CalledProcessError as e:
        return (
            jsonify(
                {"error": f"vnstat вернул код ошибки: {e.returncode}", "iface": iface}
            ),
            500,
        )
    except Exception as e:
        return jsonify({"error": str(e), "iface": iface}), 500

    # Извлекаем массив данных
    traffic_data = []
    for it in data.get("interfaces", []):
        if it.get("name") == iface:
            traffic = it.get("traffic") or {}
            if vnstat_option == "f":
                traffic_data = traffic.get("fiveminute") or []
            elif vnstat_option == "h":
                traffic_data = traffic.get("hour") or []
            elif vnstat_option == "d":
                traffic_data = traffic.get("day") or []
            break

    # Сортировка по дате
    def sort_key(h):
        d = h.get("date") or {}
        t = h.get("time") or {}
        return (
            d.get("year", 0),
            d.get("month", 0),
            d.get("day", 0),
            t.get("hour", 0),
            t.get("minute", 0),
        )

    sorted_data = sorted(traffic_data, key=sort_key)
    if points:
        sorted_data = sorted_data[-points:]

    labels, utc_labels, rx_mbps, tx_mbps = [], [], [], []

    server_tz = datetime.now().astimezone().tzinfo  # серверный локальный timezone

    for m in sorted_data:
        d = m.get("date") or {}
        t = m.get("time") or {}

        year = int(d.get("year", 0))
        month = int(d.get("month", 0))
        day = int(d.get("day", 0))
        hour = int(t.get("hour", 0))
        minute = int(t.get("minute", 0))

        if vnstat_option == "f":
            labels.append(f"{hour:02d}:{minute:02d}")
        elif vnstat_option == "h":
            labels.append(f"{hour:02d}:00")
        else:
            labels.append(f"{day:02d}.{month:02d}")

        try:
            local_dt = datetime(year, month, day, hour, minute, tzinfo=server_tz)
        except Exception:
            local_dt = datetime.now().astimezone(server_tz)

        utc_iso = local_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        utc_labels.append(utc_iso)

        rx = int(m.get("rx", 0))
        tx = int(m.get("tx", 0))
        rx_mbps.append(round((rx * 8) / (interval_seconds * 1_000_000), 3))
        tx_mbps.append(round((tx * 8) / (interval_seconds * 1_000_000), 3))

    server_time_utc = datetime.now(timezone.utc).isoformat()

    return jsonify(
        {
            "iface": iface,
            "labels": labels,
            "utc_labels": utc_labels,
            "rx_mbps": rx_mbps,
            "tx_mbps": tx_mbps,
            "server_time": server_time_utc,
        }
    )


@app.route("/api/interfaces")
def api_interfaces():
    interfaces = get_vnstat_interfaces()
    return jsonify({"interfaces": interfaces})


@app.route("/api/cpu")
def api_cpu():

    period = request.args.get("period", "live")
    now = datetime.now()

    # Количество точек для каждого фильтра
    targets = {
        "live": LIVE_POINTS,  # 60 точек
        "hour": 60,  # 60 минут
        "day": 24,  # 24 часа
        "week": 7,  # 7 дней
        "month": 30,  # 30 дней
    }
    max_points = targets.get(period, LIVE_POINTS)

    mem_rows = list(cpu_history)

    # ----------------- LIVE -----------------
    if period == "live":
        # просто последние N точек без группировки
        last = mem_rows[-LIVE_POINTS:] if len(mem_rows) > LIVE_POINTS else mem_rows

        data = [
            {"timestamp": r["timestamp"], "cpu": r["cpu"], "ram": r["ram"]}
            for r in last
        ]

    # ----------------- Остальные периоды -----------------
    else:
        # Настройка интервала и среза
        if period == "hour":
            bucket = "minute"
            cutoff = now - timedelta(hours=1)
        elif period == "day":
            bucket = "hour"
            cutoff = now - timedelta(days=1)
        elif period == "week":
            bucket = "day"
            cutoff = now - timedelta(days=7)
        elif period == "month":
            bucket = "day"
            cutoff = now - timedelta(days=30)
        else:
            bucket = "minute"
            cutoff = now - timedelta(hours=1)

        mem_candidates = [
            r for r in mem_rows if r["timestamp"] >= cutoff
        ]  # Данные из памяти за период
        need_db = True  # Если данных в памяти недостаточно, берём из БД
        if need_db:
            try:
                conn = sqlite3.connect(app.config["SYSTEM_STATS_PATH"])
                cur = conn.cursor()

                cur.execute(
                    """
                    SELECT timestamp, cpu_percent, ram_percent
                    FROM system_stats
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                """,
                    (cutoff.strftime("%Y-%m-%d %H:%M:%S"),),
                )

                rows = cur.fetchall()
                conn.close()

                source_rows = [
                    {
                        "timestamp": datetime.strptime(ts, "%Y-%m-%d %H:%M:%S"),
                        "cpu": cpu,
                        "ram": ram,
                    }
                    for ts, cpu, ram in rows
                ]

            except Exception as e:
                print("[DB ERROR] api_cpu:", e)
                source_rows = mem_candidates
        else:
            source_rows = mem_candidates

        # Группировка по bucket (minute/hour/day)
        grouped = group_rows(source_rows, interval=bucket)
        data = resample_to_n(grouped, max_points)

    utc_labels = [
        d["timestamp"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for d in data
    ]

    return jsonify(
        {
            "utc_labels": utc_labels,
            "cpu_percent": [round(d["cpu"], 2) for d in data],
            "ram_percent": [round(d["ram"], 2) for d in data],
            "period": period,
        }
    )


if __name__ == "__main__":
    add_admin()
    app.run(debug=False, host="0.0.0.0", port=1234)
