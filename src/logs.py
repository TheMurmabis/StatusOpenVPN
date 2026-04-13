import os
import sqlite3
import csv
import json

from datetime import datetime, timedelta, timezone
from tzlocal import get_localzone

# Пути к файлам логов OpenVPN
LOG_FILES = [
    ("/etc/openvpn/server/logs/antizapret-udp-status.log", "UDP"),
    ("/etc/openvpn/server/logs/antizapret-tcp-status.log", "TCP"),
    ("/etc/openvpn/server/logs/vpn-udp-status.log", "VPN-UDP"),
    ("/etc/openvpn/server/logs/vpn-tcp-status.log", "VPN-TCP"),
]

# Путь к базе данных
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "databases", "openvpn_logs.db")
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")


def get_stats_retention_days(default_days=365):
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as settings_file:
            settings_data = json.load(settings_file)
        days = int(settings_data.get("stats_retention_days", default_days))
        return max(30, min(days, 3650))
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
        return default_days


def get_retention_windows(total_days):
    hourly_days = max(1, round(total_days * 30 / 365))
    daily_days = max(hourly_days, round(total_days * 90 / 365))
    monthly_days = max(daily_days, total_days)
    return hourly_days, daily_days, monthly_days


def initialize_database():
    """Создаёт таблицы базы данных, если их нет."""
    conn = sqlite3.connect(DB_PATH)

    # Основная таблица: почасовая статистика (хранение 30 дней)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT,
            ip_address TEXT,
            hour TEXT,
            total_bytes_received INTEGER,
            total_bytes_sent INTEGER,
            total_connections INTEGER,
            last_connected TEXT,
            UNIQUE(client_name, hour, ip_address)
        )
        """
    )

    # Агрегированная дневная статистика (хранение 90 дней)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monthly_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT,
            ip_address TEXT,
            month TEXT,
            total_bytes_received INTEGER,
            total_bytes_sent INTEGER,
            total_connections INTEGER,
            last_connected TEXT,
            UNIQUE(client_name, month, ip_address)
            )
        """
    )

    # Агрегированная месячная статистика (хранение 365 дней)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS yearly_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT,
            ip_address TEXT,
            month TEXT,
            total_bytes_received INTEGER,
            total_bytes_sent INTEGER,
            total_connections INTEGER,
            last_connected TEXT,
            UNIQUE(client_name, month, ip_address)
        )
        """
    )

    # Таблица для журналов подключений
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS connection_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT,
            local_ip TEXT,
            real_ip TEXT,
            connected_since DATETIME,
            bytes_received INTEGER,
            bytes_sent INTEGER,
            protocol TEXT
        )
    """
    )
    # Хранит последнее состояние клиентов
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS last_client_stats (
            client_name TEXT,
            ip_address TEXT,
            connected_since TEXT,
            bytes_received INTEGER,
            bytes_sent INTEGER,
            PRIMARY KEY (client_name, ip_address)
        )
    """
    )

    conn.commit()
    conn.close()


def ensure_column_exists():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(monthly_stats)")
        columns = [row[1] for row in cursor.fetchall()]
        if "last_connected" not in columns:
            cursor.execute("ALTER TABLE monthly_stats ADD COLUMN last_connected TEXT")
            conn.commit()


def mask_ip(ip_address):
    if not ip_address:
        return "0.0.0.0"  # значение по умолчанию

    ip = ip_address.split(":")[0]
    parts = ip.split(".")

    if len(parts) == 4:
        try:
            parts = [str(int(part)) for part in parts]
            return f"{parts[0]}.{parts[1]}.{parts[2]}.{parts[3]}"
        except ValueError:
            return ip

    return ip_address


def format_date(date_string):
    date_obj = datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
    server_timezone = get_localzone()
    localized_date = date_obj.replace(tzinfo=server_timezone)
    utc_date = localized_date.astimezone(timezone.utc)
    return utc_date.isoformat()


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


def normalize_real_address(addr):
    # OpenVPN 2.7: udp4:IP:PORT или tcp4:IP:PORT
    if addr.startswith(("udp4:", "tcp4:", "tcp4-server:", "udp6:", "tcp6:")):
        addr = addr.split(":", 1)[1]
    return addr


def parse_log_file(log_file, protocol):
    """Читает и парсит файл лога."""
    logs = []
    total_received = 0
    total_sent = 0
    parse_count = 0
    skipped_count = 0
    if not os.path.exists(log_file):
        print(f"Файл не найден: {log_file}")
        return []

    with open(log_file, newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        next(reader)

        for row in reader:
            if row[0] == "CLIENT_LIST":
                parse_count += 1
                client_name = row[1]
                real_address = normalize_real_address(row[2])
                received = int(row[5])
                sent = int(row[6])
                total_received += received
                total_sent += sent
                start_date = datetime.strptime(row[7], "%Y-%m-%d %H:%M:%S")
                duration = format_duration(start_date)
                logs.append(
                    {
                        "client_name": client_name,
                        "real_ip": mask_ip(real_address),
                        "local_ip": row[3],
                        "bytes_received": received,
                        "connected_since": format_date(row[7]),
                        "bytes_sent": sent,
                        "duration": duration,
                        "protocol": protocol,
                    }
                )
                print(f"Обработано: {client_name}_{received}/{sent}")
    return logs


def save_daily_stats(logs):
    """Сохраняет суммарные данные в таблицу daily_stats с почасовой гранулярностью."""

    current_hour = datetime.today().strftime("%Y-%m-%d %H:00")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        aggregated_data = {}

        for log in logs:
            try:
                connected_since = datetime.fromisoformat(log["connected_since"])
            except (ValueError, TypeError):
                continue

            client_name = log["client_name"]
            ip_address = log["local_ip"]
            new_bytes_received = log.get("bytes_received", 0)
            new_bytes_sent = log.get("bytes_sent", 0)

            cursor.execute(
                """
                SELECT connected_since, bytes_received, bytes_sent 
                FROM last_client_stats 
                WHERE client_name = ? AND ip_address = ?
                """,
                (client_name, ip_address),
            )
            last_state = cursor.fetchone()

            if last_state:
                last_connected_since, last_bytes_received, last_bytes_sent = last_state

                if last_connected_since != log["connected_since"]:
                    diff_received = new_bytes_received
                    diff_sent = new_bytes_sent
                else:
                    diff_received = max(0, new_bytes_received - last_bytes_received)
                    diff_sent = max(0, new_bytes_sent - last_bytes_sent)
            else:
                diff_received = new_bytes_received
                diff_sent = new_bytes_sent

            key = (client_name, ip_address, current_hour)
            if key not in aggregated_data:
                aggregated_data[key] = {
                    "total_bytes_received": 0,
                    "total_bytes_sent": 0,
                    "total_connections": 0,
                }

            aggregated_data[key]["total_bytes_received"] += diff_received
            aggregated_data[key]["total_bytes_sent"] += diff_sent
            aggregated_data[key]["total_connections"] += 1

            aggregated_data[key]["last_connected"] = max(
                aggregated_data[key].get("last_connected", connected_since),
                connected_since,
            )

            cursor.execute(
                """
                INSERT INTO last_client_stats (client_name, ip_address, connected_since, bytes_received, bytes_sent)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(client_name, ip_address) DO UPDATE SET
                connected_since = excluded.connected_since,
                bytes_received = excluded.bytes_received,
                bytes_sent = excluded.bytes_sent
                """,
                (
                    client_name,
                    ip_address,
                    log["connected_since"],
                    new_bytes_received,
                    new_bytes_sent,
                ),
            )

        for (client_name, ip_address, hour), data in aggregated_data.items():
            cursor.execute(
                """
                SELECT total_bytes_received, total_bytes_sent, total_connections, last_connected 
                FROM daily_stats WHERE client_name = ? AND ip_address = ? AND hour = ?
                """,
                (client_name, ip_address, hour),
            )
            existing_log = cursor.fetchone()

            if existing_log:
                (
                    existing_bytes_received,
                    existing_bytes_sent,
                    existing_connections,
                    existing_last_connected,
                ) = existing_log
                last_connected = max(
                    existing_last_connected or "", data["last_connected"].isoformat()
                )

                cursor.execute(
                    """
                    UPDATE daily_stats
                    SET total_bytes_received = total_bytes_received + ?, 
                        total_bytes_sent = total_bytes_sent + ?, 
                        total_connections = total_connections + ?,
                        last_connected = ?
                    WHERE client_name = ? AND ip_address = ? AND hour = ?
                    """,
                    (
                        data["total_bytes_received"],
                        data["total_bytes_sent"],
                        data["total_connections"],
                        last_connected,
                        client_name,
                        ip_address,
                        hour,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO daily_stats (client_name, ip_address, hour, total_bytes_received, total_bytes_sent, total_connections, last_connected)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        client_name,
                        ip_address,
                        hour,
                        data["total_bytes_received"],
                        data["total_bytes_sent"],
                        data["total_connections"],
                        data["last_connected"].isoformat(),
                    ),
                )
        conn.commit()


def aggregate_to_monthly():
    """Агрегирует почасовые данные из daily_stats в дневные данные в monthly_stats."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO monthly_stats
                (client_name, ip_address, month,
                 total_bytes_received, total_bytes_sent,
                 total_connections, last_connected)
            SELECT client_name, ip_address, substr(hour, 1, 10),
                   SUM(total_bytes_received), SUM(total_bytes_sent),
                   SUM(total_connections), MAX(last_connected)
            FROM daily_stats
            GROUP BY client_name, ip_address, substr(hour, 1, 10)
            ON CONFLICT(client_name, month, ip_address) DO UPDATE SET
                total_bytes_received = excluded.total_bytes_received,
                total_bytes_sent = excluded.total_bytes_sent,
                total_connections = excluded.total_connections,
                last_connected = excluded.last_connected
            """
        )
        conn.commit()


def aggregate_to_yearly():
    """Агрегирует дневные данные из monthly_stats в месячные данные в yearly_stats."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO yearly_stats
                (client_name, ip_address, month,
                 total_bytes_received, total_bytes_sent,
                 total_connections, last_connected)
            SELECT client_name, ip_address, substr(month, 1, 7),
                   SUM(total_bytes_received), SUM(total_bytes_sent),
                   SUM(total_connections), MAX(last_connected)
            FROM monthly_stats
            GROUP BY client_name, ip_address, substr(month, 1, 7)
            ON CONFLICT(client_name, month, ip_address) DO UPDATE SET
                total_bytes_received = excluded.total_bytes_received,
                total_bytes_sent = excluded.total_bytes_sent,
                total_connections = excluded.total_connections,
                last_connected = excluded.last_connected
            """
        )
        conn.commit()


def cleanup_old_stats(total_days=None):
    """Очищает устаревшие записи из всех таблиц статистики."""
    retention_days = total_days or get_stats_retention_days(default_days=365)
    hourly_days, daily_days, monthly_days = get_retention_windows(retention_days)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        hourly_cutoff = (datetime.today() - timedelta(days=hourly_days)).strftime("%Y-%m-%d")
        cursor.execute("DELETE FROM daily_stats WHERE hour < ?", (hourly_cutoff,))

        daily_cutoff = (datetime.today() - timedelta(days=daily_days)).strftime("%Y-%m-%d")
        cursor.execute(
            "DELETE FROM monthly_stats WHERE month < ? OR length(month) != 10",
            (daily_cutoff,),
        )

        monthly_cutoff = (datetime.today() - timedelta(days=monthly_days)).strftime("%Y-%m")
        cursor.execute("DELETE FROM yearly_stats WHERE month < ?", (monthly_cutoff,))

        conn.commit()


def save_connection_logs(logs):
    """Сохраняет данные подключений в таблицу connection_logs, избегая повторных записей и добавляя только разницу в трафике."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        for log in logs:
            # Проверяем, существует ли уже запись с такими же client_name и connected_since
            cursor.execute(
                """
                SELECT id, bytes_received, bytes_sent FROM connection_logs 
                WHERE client_name = ? AND connected_since = ?
                LIMIT 1
                """,
                (log["client_name"], log["connected_since"]),
            )
            existing_log = cursor.fetchone()

            if existing_log is None:
                # Если записи нет, добавляем новую
                cursor.execute(
                    """
                    INSERT INTO connection_logs (client_name, local_ip, real_ip, connected_since, bytes_received, bytes_sent, protocol)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        log["client_name"],
                        log["local_ip"],
                        log["real_ip"],
                        log["connected_since"],
                        log["bytes_received"],
                        log["bytes_sent"],
                        log["protocol"],
                    ),
                )
            else:
                # Если запись существует, вычисляем разницу в трафике
                existing_id, existing_bytes_received, existing_bytes_sent = existing_log

                # Вычисляем разницу
                diff_received = log["bytes_received"] - existing_bytes_received
                diff_sent = log["bytes_sent"] - existing_bytes_sent

                # Если разница больше нуля, обновляем данные
                if diff_received > 0 or diff_sent > 0:
                    cursor.execute(
                        """
                        UPDATE connection_logs
                        SET bytes_received = bytes_received + ?, bytes_sent = bytes_sent + ?
                        WHERE id = ?
                        """,
                        (diff_received, diff_sent, existing_id),
                    )

            # Удаляем старые записи, если их больше 100
            cursor.execute(
                """
                DELETE FROM connection_logs
                WHERE id NOT IN (
                    SELECT id FROM connection_logs ORDER BY id DESC LIMIT 100
                )
                """
            )

        conn.commit()


def process_logs():
    """Основная функция для обработки логов."""
    initialize_database()
    ensure_column_exists()
    all_logs = []
    for log_file, protocol in LOG_FILES:
        all_logs.extend(parse_log_file(log_file, protocol))
    save_daily_stats(all_logs)
    save_connection_logs(all_logs)
    aggregate_to_monthly()
    aggregate_to_yearly()
    cleanup_old_stats()


if __name__ == "__main__":
    process_logs()
