"""Аудит действий администраторов в боте и веб-интерфейсе."""

import os
import sqlite3
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT_DB_PATH = os.path.join(BASE_DIR, "databases", "admin_audit.db")

RETENTION_DAYS = 30


def _get_conn():
    """Получить подключение к БД и создать таблицу при необходимости."""
    conn = sqlite3.connect(AUDIT_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            source TEXT NOT NULL,
            admin_id TEXT NOT NULL,
            admin_name TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT DEFAULT '',
            ip_address TEXT DEFAULT ''
        )
    """)
    conn.commit()
    return conn


def _cleanup_old_logs(conn):
    """Удалить записи старше RETENTION_DAYS."""
    cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).isoformat()
    conn.execute("DELETE FROM admin_log WHERE timestamp < ?", (cutoff,))
    conn.commit()


def log_action(
    source: str,
    admin_id: str,
    admin_name: str,
    action: str,
    details: str = "",
    ip_address: str = "",
):
    """Записать действие администратора в БД.

    Аргументы:
        source: 'bot' или 'web'
        admin_id: ID Telegram или имя пользователя веб-интерфейса
        admin_name: Отображаемое имя
        action: Тип действия (client_create, client_delete и т.д.)
        details: Дополнительные данные (имя клиента и т.д.)
        ip_address: IP-адрес для веб-входов
    """
    with _get_conn() as conn:
        _cleanup_old_logs(conn)
        conn.execute(
            """INSERT INTO admin_log 
               (timestamp, source, admin_id, admin_name, action, details, ip_address)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(),
                source,
                str(admin_id),
                admin_name,
                action,
                details,
                ip_address,
            ),
        )
        conn.commit()


def get_logs(limit: int = 50, offset: int = 0, action_filter: str = None):
    """Получить записи аудита из БД.

    Аргументы:
        limit: Максимальное количество записей
        offset: Сколько записей пропустить
        action_filter: Фильтр по типу действия (необязательно)

    Возвращает:
        Список записей в виде словарей
    """
    with _get_conn() as conn:
        if action_filter:
            rows = conn.execute(
                """SELECT * FROM admin_log 
                   WHERE action = ?
                   ORDER BY id DESC LIMIT ? OFFSET ?""",
                (action_filter, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM admin_log 
                   ORDER BY id DESC LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]


def get_logs_count(action_filter: str = None) -> int:
    """Получить общее количество записей аудита."""
    with _get_conn() as conn:
        if action_filter:
            result = conn.execute(
                "SELECT COUNT(*) FROM admin_log WHERE action = ?",
                (action_filter,),
            ).fetchone()
        else:
            result = conn.execute("SELECT COUNT(*) FROM admin_log").fetchone()
        return result[0] if result else 0


async def notify_admins(actor_id: int, actor_name: str, action_text: str):
    """Уведомить всех админов (кроме исполнителя) о важном действии через Telegram.

    Аргументы:
        actor_id: ID Telegram администратора, выполнившего действие
        actor_name: Отображаемое имя администратора
        action_text: Человекочитаемое описание действия
    """
    from .bot import get_bot
    from .config import get_admin_ids

    bot = get_bot()
    if not bot:
        return

    text = f"⚡ <b>{actor_name}</b> {action_text}"

    for admin_id in get_admin_ids():
        if admin_id == actor_id:
            continue
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass
