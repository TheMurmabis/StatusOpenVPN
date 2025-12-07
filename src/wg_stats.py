#!/root/web/venv/bin/python
"""empty"""

from datetime import datetime, timedelta
import os
import time
import sqlite3
import subprocess
import schedule

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "databases" , "wireguard_stats.db")

SAVE_TIME = "23:59"  # Время для фиксирования дневного трафика
START_TIME = "00:00"  # Время для начала записи нового дня
EVERY_TIME = 30  # Интервал сохранения дневного и общего трафика в секундах
SYNS_TIME = 5  # Интервал синхронизации клиентов в минутах


def init_db():
    """Инициализация базы данных"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS wg_daily_stats (
                date TEXT NOT NULL,
                peer TEXT NOT NULL,
                client TEXT NOT NULL,
                received INTEGER NOT NULL,
                sent INTEGER NOT NULL,
                interface TEXT NOT NULL,
                PRIMARY KEY (date, peer, interface)
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS wg_intermediate (
                peer TEXT NOT NULL,
                interface TEXT NOT NULL,
                last_received INTEGER NOT NULL,
                last_sent INTEGER NOT NULL,
                date TEXT NOT NULL,
                PRIMARY KEY (peer, interface)
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS wg_total_stats (
                peer TEXT NOT NULL,
                client TEXT NOT NULL,
                total_received INTEGER NOT NULL,
                total_sent INTEGER NOT NULL,
                interface TEXT NOT NULL,
                PRIMARY KEY (peer, interface)
            )
        """
        )
        conn.commit()


init_db()


def convert_to_bytes(value):
    """Преобразует значение в байты."""
    units = {
        "B": 1,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "TiB": 1024**4,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
    }

    if isinstance(value, (int, float)):
        return int(value)

    if isinstance(value, str):
        value = value.strip()

        if not value or value in ("0 B", "0B"):
            return 0

        parts = value.split()
        if len(parts) == 1:
            if parts[0].isdigit():
                return int(parts[0])
            else:
                return 0
        elif len(parts) == 2:
            num, unit = parts
            if unit in units:
                return int(float(num) * units[unit])
            else:
                return 0
        else:
            return 0
    return 0


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
    return client_mapping


def get_wireguard_stats():
    """Получение данных из wg show"""
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


def get_wg_intermediate(data="all"):
    """Получение данных с таблицы wg_intermediate"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        if data == "all":
            cursor.execute("""SELECT * from wg_intermediate""")
            intermediate = cursor.fetchall()
            return intermediate

        if data == "date":
            cursor.execute("""SELECT date from wg_intermediate""")
            return [row[0] for row in cursor.fetchall()][0]

        conn.commit()


def get_wg_daily_stats():
    """Получение данных с таблицы wg_daily_stats"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM wg_daily_stats")
        return cursor.fetchall()


def get_wg_total_stats():
    """Получение данных с таблицы wg_total_stats"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""SELECT * from wg_total_stats""")
        conn.commit()
        return cursor.fetchall()


def clear_wg_total_stats():
    """Очистка таблицы wg_total_stats от лишних записей"""
    try:
        output = get_wireguard_stats()
        stats = parse_wireguard_stats(output)

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            current_peers = {(data["peer"], data["interface"]) for data in stats}

            cursor.execute("SELECT peer, interface FROM wg_total_stats")
            db_peers = set(cursor.fetchall())

            peers_to_remove = db_peers - current_peers
            for peer, interface in peers_to_remove:
                cursor.execute(
                    "DELETE FROM wg_total_stats WHERE peer = ? AND interface = ?",
                    (peer, interface),
                )
                conn.commit()
                return True  # Успешное выполнение

    except sqlite3.Error as e:
        print(f"Ошибка SQLite при очистке таблицы: {e}")
        return False


def parse_wireguard_stats(output):
    """Парсинг вывода wg show, извлекаем только peer, client, received, sent, interface."""
    stats = []
    lines = output.strip().splitlines()
    interface_name = None  # Текущий интерфейс
    vpn_mapping = read_wg_config("/etc/wireguard/vpn.conf")
    antizapret_mapping = read_wg_config("/etc/wireguard/antizapret.conf")
    client_mapping = {**vpn_mapping, **antizapret_mapping}

    for line in lines:
        line = line.strip()
        if line.startswith("interface:"):
            interface_name = line.split(": ")[1]  # Запоминаем интерфейс
        elif line.startswith("peer:"):
            peer = line.split(": ")[1].strip()
            client_name = client_mapping.get(peer, "Unknown")
            stats.append(
                {
                    "peer": peer,
                    "client": client_name,
                    "received": "0 B",  # Заполняем, обновится ниже
                    "sent": "0 B",
                    "interface": interface_name if interface_name else "Unknown",
                }
            )
        elif line.startswith("transfer:") and stats:
            transfer_data = line.split(":")[1].strip().split(", ")
            stats[-1]["received"] = transfer_data[0].replace(" received", "").strip()
            stats[-1]["sent"] = transfer_data[1].replace(" sent", "").strip()

    return stats


def save_wg_stats():
    """Функция сохранения статистики"""
    output = get_wireguard_stats()
    stats = parse_wireguard_stats(output)

    now = datetime.now().strftime("%H:%M:%S")
    # print(f"Сохранение статистики: {now}")
    clean_old_daily_stats(days=7)

    # if not stats:
    #     print("❌ Нет данных для сохранения! Проверяем wg show...")
    #     print(output)  # Посмотри, что возвращает wg

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        now = datetime.now()

        for data in stats:
            peer = data["peer"]
            date = datetime.now().strftime("%Y-%m-%d")
            client = data["client"]
            received_now = convert_to_bytes(data["received"])
            sent_now = convert_to_bytes(data["sent"])
            interface = data["interface"]

            if now.hour == 0 and now.minute == 0 and now.second == 1:
                cursor.execute(
                    """INSERT OR REPLACE INTO wg_intermediate 
                    (peer, interface, last_received, last_sent, date) 
                    VALUES (?, ?, ?, ?, ?)""",
                    (peer, interface, received_now, sent_now, date),
                )
                conn.commit()
            cursor.execute(
                """INSERT OR REPLACE INTO wg_total_stats 
                (peer, client, total_received, total_sent, interface)
                VALUES (?, ?, ?, ?, ?)
            """,
                (peer, client, received_now, sent_now, interface),
            )
            conn.commit()


def save_daily_stats(dailysave=False):
    """Функция сохранения статистики за день"""
    output = get_wireguard_stats()
    stats = parse_wireguard_stats(output)
    date = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M:%S")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        if dailysave:
            # Фиксирование дневной статистики в wg_intermediate
            print(f"Фиксирование дневной статистики: {now}")
            for data in stats:
                try:
                    cursor.execute(
                        """INSERT OR REPLACE INTO wg_intermediate
                        (peer, interface, last_received, last_sent, date) 
                        VALUES (?, ?, ?, ?, ?)""",
                        (
                            data["peer"],
                            data["interface"],
                            convert_to_bytes(data["received"]),
                            convert_to_bytes(data["sent"]),
                            date,
                        ),
                    )
                except sqlite3.Error as e:
                    print(f"Ошибка при сохранении {data['peer']}: {e}")

            conn.commit()
            return True

        else:
            # Ежедневное сохранение статистики в wg_daily_stats
            try:
                # Получаем текущие данные
                current_stats = get_wg_total_stats()
                intermediate_stats = get_wg_intermediate()

                # Создаем словарь для быстрого поиска
                intermediate_dict = {
                    (row[0], row[1]): row for row in intermediate_stats
                }

                for stats_row in current_stats:
                    peer, client = stats_row[0], stats_row[1]
                    interface = stats_row[4]
                    key = (peer, interface)

                    if key in intermediate_dict:
                        inter_row = intermediate_dict[key]
                        # # Вычисляем разницу
                        # received_diff = int(stats_row[2]) - int(inter_row[2])
                        # sent_diff = int(stats_row[3]) - int(inter_row[3])

                        # Вычисляем разницу с защитой от отрицательных значений
                        # received_diff = max(0, int(stats_row[2]) - int(inter_row[2]))
                        # sent_diff = max(0, int(stats_row[3]) - int(inter_row[3]))

                        current_received = int(stats_row[2])
                        current_sent = int(stats_row[3])
                        last_received = int(inter_row[2])
                        last_sent = int(inter_row[3])

                        if (
                            current_received >= last_received
                            and current_sent >= last_sent
                        ):
                            # Обычная разница
                            received_diff = current_received - last_received
                            sent_diff = current_sent - last_sent
                        else:
                            # Сброс интерфейса - сохраняем всё что есть
                            print(
                                f"Обнаружен сброс счетчиков для {peer} на {interface}."
                            )
                            received_diff = current_received
                            sent_diff = current_sent

                        # Проверяем существование записи
                        cursor.execute(
                            """SELECT 1 FROM wg_daily_stats 
                            WHERE date = ? AND peer = ? AND interface = ?""",
                            (date, peer, interface),
                        )
                        exists = cursor.fetchone()

                        if exists:
                            cursor.execute(
                                """UPDATE wg_daily_stats 
                                SET received = ?, sent = ?, client = ?
                                WHERE date = ? AND peer = ? AND interface = ?""",
                                (
                                    convert_to_bytes(received_diff),
                                    convert_to_bytes(sent_diff),
                                    client,
                                    date,
                                    peer,
                                    interface,
                                ),
                            )
                        else:
                            cursor.execute(
                                """INSERT INTO wg_daily_stats 
                                (date, peer, client, received, sent, interface) 
                                VALUES (?, ?, ?, ?, ?, ?)""",
                                (
                                    date,
                                    peer,
                                    client,
                                    convert_to_bytes(received_diff),
                                    convert_to_bytes(sent_diff),
                                    interface,
                                ),
                            )

                conn.commit()
                return True

            except Exception as e:
                print(f"Ошибка при ежедневном сохранении: {e}")
                conn.rollback()
                return False


def sync_new_peers():
    """Добавляет новые peer+interface из wg_total_stats в wg_intermediate"""
    # Очистка wg_total_stats от лишних записей
    if clear_wg_total_stats():

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            # Получаем текущую дату
            date = datetime.now().strftime("%Y-%m-%d")

            # Находим новые комбинации peer+interface, которых нет в wg_intermediate
            cursor.execute(
                """
                SELECT t.peer, t.interface 
                FROM wg_total_stats t
                LEFT JOIN wg_intermediate i 
                ON t.peer = i.peer AND t.interface = i.interface
                WHERE i.peer IS NULL
                GROUP BY t.peer, t.interface
            """
            )

            new_combinations = cursor.fetchall()

            # Добавляем новые записи
            for peer, interface in new_combinations:
                cursor.execute(
                    """
                    INSERT INTO wg_intermediate 
                    (peer, interface, last_received, last_sent, date) 
                    VALUES (?, ?, 0, 0, ?)
                """,
                    (peer, interface, date),
                )

            conn.commit()

        except sqlite3.Error as e:
            print(f"Ошибка при синхронизации новых клиентов wg_intermediate: {e}")
            conn.rollback()

        finally:
            conn.close()


# Запуск таймеров

# Обновление статистики за день
timer_1 = schedule.every(EVERY_TIME).seconds.do(save_daily_stats)
# Обновление общей статистики
timer_2 = schedule.every(EVERY_TIME).seconds.do(save_wg_stats)
# Обновление новых клиентов в wg_intermediate
timer_3 = schedule.every(SYNS_TIME).minutes.do(sync_new_peers)


def start_timers():
    """Запуск таймеров"""
    global timer_1, timer_2, timer_3
    timer_1 = schedule.every(EVERY_TIME).seconds.do(save_daily_stats)
    timer_2 = schedule.every(EVERY_TIME).seconds.do(save_wg_stats)
    timer_3 = schedule.every(SYNS_TIME).minutes.do(sync_new_peers)


def stop_timers():
    """Остановка таймеров на время фиксирования ежедневной статистики"""
    schedule.cancel_job(timer_1)
    schedule.cancel_job(timer_2)
    schedule.cancel_job(timer_3)
    time.sleep(2)
    save_daily_stats(True)


timer_stop = schedule.every().day.at(SAVE_TIME).do(stop_timers)
timer_start = schedule.every().day.at(START_TIME).do(start_timers)


def clean_old_daily_stats(days=7):
    """Удаление старых записей из wg_daily_stats"""
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Проверка наличия записей старше cutoff_date
            cursor.execute(
                """SELECT 1 FROM wg_daily_stats WHERE date < ? LIMIT 1""",
                (cutoff_date,),
            )
            if cursor.fetchone():
                # Есть записи, можно удалять
                cursor.execute(
                    """DELETE FROM wg_daily_stats WHERE date < ?""", (cutoff_date,)
                )
                conn.commit()
                print(f"Удалено записей старше {cutoff_date}")
        except sqlite3.Error as e:
            print(f"Ошибка при очистке старых записей: {e}")
            conn.rollback()


def main():
    """Основная функция"""

    print("Сохранение статистики Wireguard запущено!")

    try:
        inter_date = get_wg_intermediate("date")
    except IndexError:
        inter_date = datetime.now().strftime("%Y-%m-%d")
        save_daily_stats(True)
        time.sleep(3)

    today_date = datetime.now().strftime("%Y-%m-%d")
    if inter_date != today_date:
        save_daily_stats(True)
        clean_old_daily_stats(days=7)
        time.sleep(3)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
