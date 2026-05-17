import os
import sqlite3
from datetime import datetime, timedelta
from statistics import mean

from src.ui.constants import DB_SAVE_INTERVAL
from src.ui.extensions import app
from src.ui.state import cpu_history
from src.ui.utils.format_utils import format_bytes


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


def get_ovpn_wg_database_sizes():
    """Размеры файлов БД статистики OpenVPN и WireGuard."""
    specs = [
        ("ovpn", "OpenVPN", app.config["LOGS_DATABASE_PATH"]),
        ("wg", "WireGuard", app.config["WG_STATS_PATH"]),
    ]
    items = []
    total = 0
    for key, label, path in specs:
        try:
            sz = os.path.getsize(path)
        except OSError:
            sz = 0
        total += sz
        items.append(
            {
                "key": key,
                "label": label,
                "bytes": sz,
                "size_fmt": format_bytes(sz),
            }
        )
    return items, total


def _delete_tables_and_vacuum(db_path, tables):
    with sqlite3.connect(db_path) as conn:
        for t in tables:
            try:
                conn.execute(f"DELETE FROM {t}")
            except sqlite3.OperationalError:
                pass
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()


def clear_openvpn_stats_database():
    """Очищает openvpn_logs.db."""
    try:
        _delete_tables_and_vacuum(
            app.config["LOGS_DATABASE_PATH"],
            (
                "daily_stats",
                "monthly_stats",
                "yearly_stats",
                "connection_logs",
                "last_client_stats",
            ),
        )
        return True, None
    except Exception as e:
        return False, str(e)


def clear_wireguard_stats_database():
    """Очищает wireguard_stats.db."""
    try:
        _delete_tables_and_vacuum(
            app.config["WG_STATS_PATH"],
            (
                "wg_hourly_stats",
                "wg_daily_stats",
                "wg_monthly_stats",
                "wg_intermediate",
                "wg_total_stats",
            ),
        )
        return True, None
    except Exception as e:
        return False, str(e)


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
        cur.execute(
            "INSERT INTO system_stats (timestamp, cpu_percent, ram_percent) VALUES (?, ?, ?)",
            (now.strftime("%Y-%m-%d %H:%M:%S"), round(cpu_avg, 3), round(ram_avg, 3)),
        )

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
    """Возвращает ровно n точек, либо все данные, если их меньше."""
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
