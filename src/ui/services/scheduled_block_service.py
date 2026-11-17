import logging
import sqlite3
import time
from datetime import datetime, timezone

from src.config import Config
from src.tg_bot.audit import log_action
from src.ui.services.openvpn_service import (
    ensure_client_connect_ban_check_block,
    kick_openvpn_client,
    read_banned_clients,
    write_banned_clients,
)
logger = logging.getLogger(__name__)
RETRY_SECONDS = 60


def set_wireguard_peer_enabled(interface, peer, enable):
    # Lazy import keeps the scheduler storage usable before Flask is initialized.
    from src.ui.services.wireguard_service import set_wireguard_peer_enabled as apply

    return apply(interface, peer, enable)


def _connect():
    conn = sqlite3.connect(Config.DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_openvpn_blocks (
            client_name TEXT PRIMARY KEY,
            scheduled_at INTEGER NOT NULL,
            requested_by TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            last_attempt_at INTEGER,
            last_error TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_wireguard_disables (
            interface TEXT NOT NULL,
            peer TEXT NOT NULL,
            client_name TEXT NOT NULL DEFAULT '',
            scheduled_at INTEGER NOT NULL,
            requested_by TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            last_attempt_at INTEGER,
            last_error TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (interface, peer)
        )
        """
    )
    conn.commit()
    return conn


def schedule_openvpn_block(client_name, scheduled_at, requested_by=""):
    timestamp = int(scheduled_at.timestamp())
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO scheduled_openvpn_blocks
                (client_name, scheduled_at, requested_by, created_at,
                 last_attempt_at, last_error)
            VALUES (?, ?, ?, ?, NULL, '')
            ON CONFLICT(client_name) DO UPDATE SET
                scheduled_at = excluded.scheduled_at,
                requested_by = excluded.requested_by,
                created_at = excluded.created_at,
                last_attempt_at = NULL,
                last_error = ''
            """,
            (client_name, timestamp, str(requested_by or ""), now),
        )
        conn.commit()
    return get_scheduled_openvpn_block(client_name)


def get_scheduled_openvpn_block(client_name):
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM scheduled_openvpn_blocks WHERE client_name = ?",
            (client_name,),
        ).fetchone()
    return _serialize(row) if row else None


def get_scheduled_openvpn_blocks():
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_openvpn_blocks ORDER BY scheduled_at"
        ).fetchall()
    return {row["client_name"]: _serialize(row) for row in rows}


def cancel_scheduled_openvpn_block(client_name):
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM scheduled_openvpn_blocks WHERE client_name = ?",
            (client_name,),
        )
        conn.commit()
        return cursor.rowcount > 0


def schedule_wireguard_disable(
    interface, peer, client_name, scheduled_at, requested_by=""
):
    timestamp = int(scheduled_at.timestamp())
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO scheduled_wireguard_disables
                (interface, peer, client_name, scheduled_at, requested_by,
                 created_at, last_attempt_at, last_error)
            VALUES (?, ?, ?, ?, ?, ?, NULL, '')
            ON CONFLICT(interface, peer) DO UPDATE SET
                client_name = excluded.client_name,
                scheduled_at = excluded.scheduled_at,
                requested_by = excluded.requested_by,
                created_at = excluded.created_at,
                last_attempt_at = NULL,
                last_error = ''
            """,
            (
                str(interface),
                str(peer),
                str(client_name or ""),
                timestamp,
                str(requested_by or ""),
                now,
            ),
        )
        conn.commit()
    return get_scheduled_wireguard_disable(interface, peer)


def get_scheduled_wireguard_disable(interface, peer):
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM scheduled_wireguard_disables
            WHERE interface = ? AND peer = ?
            """,
            (str(interface), str(peer)),
        ).fetchone()
    return _serialize_wireguard(row) if row else None


def get_scheduled_wireguard_disables():
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_wireguard_disables ORDER BY scheduled_at"
        ).fetchall()
    return {
        (row["interface"], row["peer"]): _serialize_wireguard(row)
        for row in rows
    }


def cancel_scheduled_wireguard_disable(interface, peer):
    with _connect() as conn:
        cursor = conn.execute(
            """
            DELETE FROM scheduled_wireguard_disables
            WHERE interface = ? AND peer = ?
            """,
            (str(interface), str(peer)),
        )
        conn.commit()
        return cursor.rowcount > 0


def cancel_scheduled_wireguard_disables_for_client(client_name):
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM scheduled_wireguard_disables WHERE client_name = ?",
            (str(client_name or ""),),
        )
        conn.commit()
        return cursor.rowcount


def rename_scheduled_wireguard_client(old_name, new_name):
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE scheduled_wireguard_disables
            SET client_name = ?
            WHERE client_name = ?
            """,
            (str(new_name or ""), str(old_name or "")),
        )
        conn.commit()
        return cursor.rowcount


def _serialize(row):
    timestamp = int(row["scheduled_at"])
    return {
        "client_name": row["client_name"],
        "scheduled_at": datetime.fromtimestamp(
            timestamp, tz=timezone.utc
        ).isoformat(),
        "scheduled_at_timestamp": timestamp,
        "requested_by": row["requested_by"],
        "last_error": row["last_error"],
    }


def _serialize_wireguard(row):
    timestamp = int(row["scheduled_at"])
    return {
        "interface": row["interface"],
        "peer": row["peer"],
        "client_name": row["client_name"],
        "scheduled_at": datetime.fromtimestamp(
            timestamp, tz=timezone.utc
        ).isoformat(),
        "scheduled_at_timestamp": timestamp,
        "requested_by": row["requested_by"],
        "last_error": row["last_error"],
    }


def process_due_openvpn_blocks(now_timestamp=None):
    now = int(time.time() if now_timestamp is None else now_timestamp)
    retry_before = now - RETRY_SECONDS
    with _connect() as conn:
        due = conn.execute(
            """
            SELECT * FROM scheduled_openvpn_blocks
            WHERE scheduled_at <= ?
              AND (last_attempt_at IS NULL OR last_attempt_at <= ?)
            ORDER BY scheduled_at
            """,
            (now, retry_before),
        ).fetchall()

    processed = []
    for row in due:
        client_name = row["client_name"]
        try:
            ensure_client_connect_ban_check_block()
            banned_clients = read_banned_clients()
            banned_clients.add(client_name)
            write_banned_clients(banned_clients)
            kicked, errors = kick_openvpn_client(client_name, protocol=None)
            cancel_scheduled_openvpn_block(client_name)
            detail = f"{client_name} (отложенная блокировка)"
            if not kicked and errors:
                detail += "; сессия не отключена"
            log_action(
                "system",
                row["requested_by"] or "scheduler",
                row["requested_by"] or "scheduler",
                "user_ban",
                detail,
            )
            processed.append(client_name)
        except Exception as exc:
            logger.exception(
                "Не удалось выполнить отложенную блокировку %s", client_name
            )
            with _connect() as conn:
                conn.execute(
                    """
                    UPDATE scheduled_openvpn_blocks
                    SET last_attempt_at = ?, last_error = ?
                    WHERE client_name = ?
                    """,
                    (now, str(exc)[:500], client_name),
                )
                conn.commit()
    return processed


def process_due_wireguard_disables(now_timestamp=None):
    now = int(time.time() if now_timestamp is None else now_timestamp)
    retry_before = now - RETRY_SECONDS
    with _connect() as conn:
        due = conn.execute(
            """
            SELECT * FROM scheduled_wireguard_disables
            WHERE scheduled_at <= ?
              AND (last_attempt_at IS NULL OR last_attempt_at <= ?)
            ORDER BY scheduled_at
            """,
            (now, retry_before),
        ).fetchall()

    processed = []
    for row in due:
        interface = row["interface"]
        peer = row["peer"]
        client_name = row["client_name"] or (peer[:8] + "...")
        try:
            set_wireguard_peer_enabled(interface, peer, False)
            cancel_scheduled_wireguard_disable(interface, peer)
            log_action(
                "system",
                row["requested_by"] or "scheduler",
                row["requested_by"] or "scheduler",
                "peer_toggle",
                f"{client_name} (отложенное отключение, {interface})",
            )
            processed.append((interface, peer))
        except Exception as exc:
            logger.exception(
                "Не удалось выполнить отложенное отключение WireGuard %s/%s",
                interface,
                client_name,
            )
            with _connect() as conn:
                conn.execute(
                    """
                    UPDATE scheduled_wireguard_disables
                    SET last_attempt_at = ?, last_error = ?
                    WHERE interface = ? AND peer = ?
                    """,
                    (now, str(exc)[:500], interface, peer),
                )
                conn.commit()
    return processed


def scheduled_block_loop(stop_event=None, interval=15):
    while stop_event is None or not stop_event.is_set():
        processors = (
            (process_due_openvpn_blocks, "OpenVPN"),
            (process_due_wireguard_disables, "WireGuard"),
        )
        for processor, label in processors:
            try:
                processor()
            except Exception:
                # A temporary database/filesystem failure must not permanently stop
                # the scheduler thread. The next interval will retry the scan.
                logger.exception("Ошибка цикла отложенного отключения %s", label)
        if stop_event is None:
            time.sleep(interval)
        else:
            stop_event.wait(interval)
