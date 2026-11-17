"""Аудит действий администраторов в боте и веб-интерфейсе."""

import os
import sqlite3
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT_DB_PATH = os.path.join(BASE_DIR, "databases", "admin_audit.db")

RETENTION_DAYS = 30
_HIDDEN_ACTIONS = ("client_protocols_bulk_change",)


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
            ip_address TEXT DEFAULT '',
            event_key TEXT
        )
    """)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(admin_log)")}
    if "event_key" not in columns:
        conn.execute("ALTER TABLE admin_log ADD COLUMN event_key TEXT")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_log_event_key
        ON admin_log(event_key) WHERE event_key IS NOT NULL
        """
    )
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
    event_key: str = None,
    timestamp=None,
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
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()
        timestamp = str(timestamp or datetime.now().isoformat())
        conn.execute(
            """INSERT OR IGNORE INTO admin_log
               (timestamp, source, admin_id, admin_name, action, details, ip_address, event_key)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                timestamp,
                source,
                str(admin_id),
                admin_name,
                action,
                details,
                ip_address,
                event_key or None,
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
    hidden = ", ".join("?" for _ in _HIDDEN_ACTIONS)
    with _get_conn() as conn:
        if action_filter:
            if action_filter in _HIDDEN_ACTIONS:
                return []
            rows = conn.execute(
                """SELECT * FROM admin_log 
                   WHERE action = ?
                   ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?""",
                (action_filter, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""SELECT * FROM admin_log
                   WHERE action NOT IN ({hidden})
                   ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?""",
                (*_HIDDEN_ACTIONS, limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]


def format_log_details(row):
    details = str(row.get("details") or "").strip()
    if not details:
        return "—"
    action = row.get("action")
    if action == "subscription_opened":
        kind = "Временная" if row.get("admin_id") == "temporary" else "Постоянная"
        return f"{kind} публичная ссылка клиента «{details}» открыта."
    if action == "subscription_expired":
        return f"Срок временной публичной ссылки клиента «{details}» истёк."
    return details


def get_logs_count(action_filter: str = None) -> int:
    """Получить общее количество записей аудита."""
    hidden = ", ".join("?" for _ in _HIDDEN_ACTIONS)
    with _get_conn() as conn:
        if action_filter:
            if action_filter in _HIDDEN_ACTIONS:
                return 0
            result = conn.execute(
                "SELECT COUNT(*) FROM admin_log WHERE action = ?",
                (action_filter,),
            ).fetchone()
        else:
            result = conn.execute(
                f"SELECT COUNT(*) FROM admin_log WHERE action NOT IN ({hidden})",
                _HIDDEN_ACTIONS,
            ).fetchone()
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
