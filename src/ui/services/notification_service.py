import sqlite3
import time
from datetime import datetime, timedelta

from src.config import Config
from src.tg_bot.audit import RETENTION_DAYS, format_log_details, get_logs, log_action


_NOTIFICATION_META = {
    "subscription_opened": ("Публичная ссылка открыта", "link", "info"),
    "subscription_expired": ("Временная ссылка истекла", "clock-history", "warning"),
    "client_subscription_revoke": ("Публичная ссылка отозвана", "link-45deg", "warning"),
    "client_subscription_rotate": ("Публичная ссылка обновлена", "arrow-repeat", "info"),
    "client_create": ("Клиент OpenVPN создан", "person-plus", "success"),
    "client_delete": ("Клиент OpenVPN удалён", "person-dash", "warning"),
    "wg_client_create": ("Клиент WireGuard создан", "person-plus", "success"),
    "wg_client_delete": ("Клиент WireGuard удалён", "person-dash", "warning"),
    "user_ban": ("Клиент заблокирован", "person-x", "danger"),
    "client_cert_renew": ("Сертификат клиента продлён", "patch-check", "success"),
    "bot_toggle": ("Состояние Telegram-бота изменено", "telegram", "info"),
    "app_update": ("Приложение обновлено", "cloud-check", "success"),
}


def _connect():
    conn = sqlite3.connect(Config.DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_reads (
            user_id TEXT NOT NULL,
            notification_key TEXT NOT NULL,
            read_at TEXT NOT NULL,
            PRIMARY KEY (user_id, notification_key)
        )
        """
    )
    conn.commit()
    return conn


def _notification_from_log(row):
    meta = _NOTIFICATION_META.get(row.get("action"))
    if not meta:
        return None
    title, icon, level = meta
    return {
        "key": f"audit:{row['id']}",
        "timestamp": row.get("timestamp") or "",
        "title": title,
        "details": format_log_details(row),
        "icon": icon,
        "level": level,
    }


def sync_subscription_expiration_logs(now=None):
    """Persist due link expirations in audit so every UI reads one source."""
    now_ts = int(time.time()) if now is None else int(now.timestamp())
    cutoff = now_ts - RETENTION_DAYS * 24 * 60 * 60
    try:
        with sqlite3.connect(Config.DATABASE_PATH, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, client_name, expires_at
                FROM subscription_links
                WHERE link_type = 'temporary'
                  AND expires_at IS NOT NULL
                  AND expires_at <= ?
                  AND expires_at >= ?
                  AND (revoked_at IS NULL OR revoked_at >= expires_at)
                """,
                (now_ts, cutoff),
            ).fetchall()
    except sqlite3.OperationalError:
        return 0

    for row in rows:
        log_action(
            "system",
            "temporary",
            "Система",
            "subscription_expired",
            row["client_name"] or "",
            event_key=f"subscription-expired:{row['id']}",
            timestamp=datetime.fromtimestamp(row["expires_at"]),
        )
    return len(rows)


def get_notifications(limit=20):
    sync_subscription_expiration_logs()
    rows = get_logs(limit=max(200, limit))
    items = []
    for row in rows:
        item = _notification_from_log(row)
        if item:
            items.append(item)
    items.sort(key=lambda item: item["timestamp"], reverse=True)
    return items[:limit]


def get_read_notification_keys(user_id, keys):
    normalized = list(dict.fromkeys(str(key) for key in keys if key))
    if not normalized:
        return set()
    placeholders = ",".join("?" for _ in normalized)
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT notification_key FROM notification_reads
            WHERE user_id = ? AND notification_key IN ({placeholders})
            """,
            (str(user_id), *normalized),
        ).fetchall()
    return {row["notification_key"] for row in rows}


def mark_notifications_read(user_id, keys):
    normalized = list(dict.fromkeys(str(key) for key in keys if key))
    if not normalized:
        return 0
    now = datetime.now().isoformat()
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO notification_reads (user_id, notification_key, read_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, notification_key) DO UPDATE SET
                read_at = excluded.read_at
            """,
            [(str(user_id), key, now) for key in normalized],
        )
        conn.execute(
            "DELETE FROM notification_reads WHERE read_at < ?",
            ((datetime.now() - timedelta(days=90)).isoformat(),),
        )
        conn.commit()
    return len(normalized)


def mark_all_current_notifications_read(user_id):
    items = get_notifications(limit=200)
    return mark_notifications_read(user_id, [item["key"] for item in items])
