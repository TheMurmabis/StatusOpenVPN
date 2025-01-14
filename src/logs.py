import os
import sqlite3
import csv

from datetime import datetime, timezone
from tzlocal import get_localzone

# Пути к файлам логов OpenVPN
LOG_FILES = [
    ("/etc/openvpn/server/logs/antizapret-udp-status.log", "UDP"),
    ("/etc/openvpn/server/logs/antizapret-tcp-status.log", "TCP"),
    ("/etc/openvpn/server/logs/vpn-udp-status.log", "VPN-UDP"),
    ("/etc/openvpn/server/logs/vpn-tcp-status.log", "VPN-TCP"),
    ("/etc/openvpn/server/logs/antizapret-no-cipher-status.log", "NoCipher"),
]

# Путь к базе данных
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "openvpn_logs.db")


def initialize_database():
    """Создаёт таблицы базы данных, если их нет."""
    conn = sqlite3.connect(DB_PATH)

    # Таблица для ежемесячной статистики
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monthly_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT,
            month TEXT,
            total_bytes_received INTEGER,
            total_bytes_sent INTEGER,
            total_connections INTEGER,
            UNIQUE(client_name, month)
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
    conn.commit()
    conn.close()


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


def clean_client_name(name, prefix="antizapret-"):
    return name[len(prefix) :] if name.startswith(prefix) else name


def parse_log_file(log_file, protocol):
    """Читает и парсит файл лога."""
    logs = []
    total_received = 0
    total_sent = 0
    skipped_count = 0  # Счетчик пропущенных строк
    if not os.path.exists(log_file):
        print(f"Файл не найден: {log_file}")
        return []

    with open(log_file, newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        next(reader)

        for row in reader:
            if row[0] == "CLIENT_LIST":  # Печать каждой строки, которая парсится
                client_name = row[1]
                received = int(row[5])
                sent = int(row[6])
                total_received += received
                total_sent += sent
                start_date = datetime.strptime(row[7], "%Y-%m-%d %H:%M:%S")
                duration = format_duration(start_date)
                logs.append(
                    {
                        "client_name": clean_client_name(client_name),
                        "local_ip": row[2],
                        "real_ip": row[3],
                        "bytes_received": received,
                        "connected_since": format_date(row[7]),
                        "bytes_sent": sent,
                        "duration": duration,
                        "protocol": protocol,
                    }
                )
                print(f"Обработано: {row}")
            else:
                skipped_count += 1  # Увеличиваем счетчик пропущенных строк

    # Печать количества пропущенных строк
    if skipped_count > 0:
        print(f"Пропущено {skipped_count} строк(и)")

    return logs


def save_monthly_stats(logs):
    """Сохраняет суммарные данные в таблицу monthly_stats, суммируя данные по всем IP для каждого клиента."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    current_month = datetime.today().strftime("%b. %Y")
    cursor.execute("DELETE FROM monthly_stats WHERE month != ?", (current_month,))  # Удаляем старые данные

    # Словарь для агрегированных данных по каждому клиенту и месяцу
    aggregated_data = {}

    for log in logs:
        connected_since = datetime.fromisoformat(log["connected_since"])
        month = connected_since.strftime("%b. %Y")

        client_name = log["client_name"]
        new_bytes_received = log["bytes_received"]
        new_bytes_sent = log["bytes_sent"]

        # Если для этого клиента и месяца еще нет записи, создаем пустую запись в словаре
        if (client_name, month) not in aggregated_data:
            aggregated_data[(client_name, month)] = {
                "total_bytes_received": 0,
                "total_bytes_sent": 0,
                "total_connections": 0,
            }

        # Добавляем новые данные к существующему записанному значению
        aggregated_data[(client_name, month)]["total_bytes_received"] += new_bytes_received
        aggregated_data[(client_name, month)]["total_bytes_sent"] += new_bytes_sent
        aggregated_data[(client_name, month)]["total_connections"] += 1

    # После того как мы собрали все данные, записываем их в БД
    for (client_name, month), data in aggregated_data.items():
        # Проверим, существует ли запись для данного клиента и месяца
        cursor.execute(
            """
            SELECT total_bytes_received, total_bytes_sent, total_connections 
            FROM monthly_stats WHERE client_name = ? AND month = ?
            """,
            (client_name, month),
        )
        existing_log = cursor.fetchone()

        if existing_log:
            # Если запись существует, обновляем только разницу
            existing_bytes_received, existing_bytes_sent, existing_connections = existing_log
            diff_received = data["total_bytes_received"] - existing_bytes_received
            diff_sent = data["total_bytes_sent"] - existing_bytes_sent

            # Если разница положительная, обновляем
            if diff_received > 0 or diff_sent > 0:
                cursor.execute(
                    """
                    UPDATE monthly_stats
                    SET total_bytes_received = total_bytes_received + ?, 
                        total_bytes_sent = total_bytes_sent + ?, 
                        total_connections = total_connections + ?
                    WHERE client_name = ? AND month = ?
                    """,
                    (
                        diff_received,
                        diff_sent,
                        data["total_connections"],
                        client_name,
                        month,
                    ),
                )
        else:
            # Если записи нет, добавляем новую
            cursor.execute(
                """
                INSERT INTO monthly_stats (client_name, month, total_bytes_received, total_bytes_sent, total_connections)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    client_name,
                    month,
                    data["total_bytes_received"],
                    data["total_bytes_sent"],
                    data["total_connections"],
                ),
            )

    conn.commit()
    conn.close()






def save_connection_logs(logs):
    """Сохраняет данные подключений в таблицу connection_logs, избегая повторных записей и добавляя только разницу в трафике."""
    conn = sqlite3.connect(DB_PATH)
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
    conn.close()



def process_logs():
    """Основная функция для обработки логов."""
    initialize_database()
    all_logs = []
    for log_file, protocol in LOG_FILES:
        all_logs.extend(parse_log_file(log_file, protocol))
    save_monthly_stats(all_logs)
    save_connection_logs(all_logs)


if __name__ == "__main__":
    process_logs()
