import hashlib
import os
import re
import secrets
import sqlite3
import threading
import time
import ipaddress
import fcntl
from datetime import datetime, timezone

from cryptography import x509
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.backends import default_backend

from src.config import Config
from src.ui.constants import (
    CLIENT_NAME_PATTERN,
    ENV_PATH,
    OPENVPN_SUBSCRIPTION_SLUG_PATTERN,
    OPENVPN_SUBSCRIPTION_TOKEN_PATTERN,
    STATUSOPENVPN_SETUP_PATH,
)
from src.ui.services.env_service import read_setup_key_value_file
from src.ui.utils.network_utils import get_external_ip
from src.ui.utils.openvpn_naming import clean_client_display_name, list_openvpn_profile_choices
from src.ui.utils.wireguard_naming import list_wireguard_profile_choices


_KEY_LOCK = threading.Lock()
_KEY_RECOVERY_LOCK = threading.Lock()
_FERNET = None
_FERNET_FINGERPRINT = None
_RECOVERED_FINGERPRINT = None
_PREVIEW_UA_RE = re.compile(
    r"TelegramBot|Twitterbot|facebookexternalhit|Facebot|Slackbot|"
    r"Discordbot|LinkedInBot|SkypeUriPreview|Iframely|Embedly|"
    r"Pinterest|Googlebot|bingbot|YandexBot|Applebot|Slack-ImgProxy",
    re.I,
)


def is_preview_request(user_agent=None, method=None):
    if (method or "").upper() == "HEAD":
        return True
    return bool(_PREVIEW_UA_RE.search(user_agent or ""))


def _setup_map():
    pairs, error = read_setup_key_value_file(STATUSOPENVPN_SETUP_PATH)
    if error:
        return {}
    return {key: value for key, value in pairs}


def _is_dns_hostname(value):
    host = (value or "").strip().lower().rstrip(".")
    if not host or "/" in host or ":" in host or " " in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        return "." in host


def _cert_is_currently_valid(cert_path):
    if not os.path.isfile(cert_path):
        return False
    try:
        with open(cert_path, "rb") as handle:
            cert = x509.load_pem_x509_certificate(handle.read(), default_backend())
        expiry = getattr(cert, "not_valid_after_utc", None)
        if expiry is None:
            expiry = cert.not_valid_after
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return expiry > now
    except Exception:
        return False


def is_subscription_https_ready():
    return get_subscription_https_diagnostics()["ready"]


def subscriptions_preference_enabled():
    from src.ui.services.settings_service import read_settings

    return bool(read_settings().get("subscriptions_enabled", False))


def are_subscriptions_active():
    return subscriptions_preference_enabled() and is_subscription_https_ready()


def subscriptions_unavailable_message():
    if not is_subscription_https_ready():
        return "Ссылки доступны только при домене и действующем HTTPS-сертификате."
    return "Публичные ссылки выключены в настройках."


def resolve_subscriptions_enabled(posted_on, https_ready):
    if not https_ready:
        return subscriptions_preference_enabled()
    return bool(posted_on)


def get_subscription_https_diagnostics():
    setup = _setup_map()
    domain = (setup.get("DOMAIN") or "").strip()
    server_url = (setup.get("SERVER_URL") or "").strip()
    https_enabled = (setup.get("HTTPS_ENABLED") or "").strip() == "1"
    domain_ready = _is_dns_hostname(domain)
    server_url_ready = server_url.lower().startswith("https://")
    cert_path = os.path.join("/etc/letsencrypt/live", domain, "fullchain.pem")
    certificate_ready = domain_ready and _cert_is_currently_valid(cert_path)
    return {
        "ready": bool(
            https_enabled and domain_ready and server_url_ready and certificate_ready
        ),
        "https_enabled": https_enabled,
        "domain_ready": domain_ready,
        "domain": domain,
        "server_url_ready": server_url_ready,
        "server_url": server_url,
        "certificate_ready": certificate_ready,
    }


def get_public_base_url():
    pairs, error = read_setup_key_value_file(STATUSOPENVPN_SETUP_PATH)
    if not error:
        for key, value in pairs:
            if key == "SERVER_URL":
                url = (value or "").strip().rstrip("/")
                if url:
                    return url
    try:
        from flask import has_request_context, request

        if has_request_context():
            root = (request.url_root or "").rstrip("/")
            script = (request.script_root or "").rstrip("/")
            if script and not root.endswith(script):
                return f"{root}{script}"
            return root
    except Exception:
        pass
    return ""


def subscription_page_url(token):
    base = get_public_base_url()
    if not base or not token:
        return ""
    return f"{base}/s/{token}"


def _normalize_telegram_id(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text.isdigit():
        return None
    return text


def _is_temporary(record):
    if not isinstance(record, dict):
        return True
    if "temporary" not in record:
        return True
    return bool(record.get("temporary"))


def get_subscription_link_lifetime_seconds():
    from src.ui.services.settings_service import get_subscription_link_lifetime_minutes

    return get_subscription_link_lifetime_minutes() * 60


def _env_value(lines, key):
    prefix = f"{key}="
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()
    return ""


def _get_fernet():
    """Return the shared token cipher, creating its key once when necessary."""
    global _FERNET, _FERNET_FINGERPRINT

    if _FERNET is None:
        with _KEY_LOCK:
            if _FERNET is None:
                configured = (os.environ.get("SUBSCRIPTION_TOKEN_KEY") or "").strip()
                if not configured:
                    directory = os.path.dirname(ENV_PATH)
                    os.makedirs(directory, exist_ok=True)
                    with open(ENV_PATH, "a+", encoding="utf-8") as env_file:
                        fcntl.flock(env_file.fileno(), fcntl.LOCK_EX)
                        try:
                            env_file.seek(0)
                            lines = env_file.readlines()
                            configured = _env_value(lines, "SUBSCRIPTION_TOKEN_KEY")
                            if not configured:
                                configured = Fernet.generate_key().decode("ascii")
                                env_file.seek(0, os.SEEK_END)
                                if lines and not lines[-1].endswith("\n"):
                                    env_file.write("\n")
                                env_file.write(f"SUBSCRIPTION_TOKEN_KEY={configured}\n")
                                env_file.flush()
                                os.fsync(env_file.fileno())
                            try:
                                os.chmod(ENV_PATH, 0o600)
                            except OSError:
                                pass
                        finally:
                            fcntl.flock(env_file.fileno(), fcntl.LOCK_UN)

                _FERNET = Fernet(configured.encode("ascii"))
                _FERNET_FINGERPRINT = hashlib.sha256(
                    configured.encode("ascii")
                ).hexdigest()

    _recover_permanent_links_for_current_key()
    return _FERNET


def _recover_permanent_links_for_current_key():
    """Rotate active permanent links unreadable with the current key."""
    global _RECOVERED_FINGERPRINT

    fingerprint = _FERNET_FINGERPRINT
    cipher = _FERNET
    if not fingerprint or cipher is None or _RECOVERED_FINGERPRINT == fingerprint:
        return []

    with _KEY_RECOVERY_LOCK:
        if _RECOVERED_FINGERPRINT == fingerprint:
            return []

        now = int(time.time())
        rotated = []
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            groups = conn.execute(
                """
                SELECT client_name, telegram_id
                FROM subscription_links
                WHERE link_type = 'permanent' AND revoked_at IS NULL
                GROUP BY client_name, telegram_id
                """
            ).fetchall()
            for group in groups:
                client_name = group["client_name"]
                telegram_id = group["telegram_id"]
                row = conn.execute(
                    """
                    SELECT token_encrypted
                    FROM subscription_links
                    WHERE client_name = ? AND telegram_id = ?
                      AND link_type = 'permanent' AND revoked_at IS NULL
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """,
                    (client_name, telegram_id),
                ).fetchone()
                try:
                    token = cipher.decrypt(
                        str(row["token_encrypted"]).encode("ascii")
                    ).decode("utf-8")
                except (InvalidToken, ValueError, UnicodeError):
                    token = None
                if token and OPENVPN_SUBSCRIPTION_TOKEN_PATTERN.fullmatch(token):
                    continue

                new_token = None
                new_id = None
                for _ in range(8):
                    candidate = secrets.token_urlsafe(24)
                    if not OPENVPN_SUBSCRIPTION_TOKEN_PATTERN.fullmatch(candidate):
                        continue
                    try:
                        cursor = conn.execute(
                            """
                            INSERT INTO subscription_links(
                                token_hash, token_encrypted, client_name,
                                telegram_id, link_type, created_at
                            ) VALUES (?, ?, ?, ?, 'permanent', ?)
                            """,
                            (
                                _token_hash(candidate),
                                cipher.encrypt(candidate.encode("utf-8")).decode(
                                    "ascii"
                                ),
                                client_name,
                                telegram_id,
                                now,
                            ),
                        )
                    except sqlite3.IntegrityError:
                        continue
                    new_token = candidate
                    new_id = cursor.lastrowid
                    break
                if not new_token or new_id is None:
                    raise RuntimeError("Не удалось перевыпустить постоянную ссылку")

                conn.execute(
                    """
                    UPDATE subscription_links SET revoked_at = ?
                    WHERE client_name = ? AND telegram_id = ?
                      AND link_type = 'permanent' AND revoked_at IS NULL
                      AND id != ?
                    """,
                    (now, client_name, telegram_id, new_id),
                )
                rotated.append((client_name, telegram_id, new_token))
            conn.commit()

        _RECOVERED_FINGERPRINT = fingerprint
        return rotated


def reset_subscription_key_recovery():
    """Recheck restored subscription rows on the next link operation."""
    global _RECOVERED_FINGERPRINT
    with _KEY_RECOVERY_LOCK:
        _RECOVERED_FINGERPRINT = None


def _token_hash(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _encrypt_token(token):
    return _get_fernet().encrypt(str(token).encode("utf-8")).decode("ascii")


def _decrypt_token(ciphertext):
    if not ciphertext:
        return None
    try:
        return _get_fernet().decrypt(str(ciphertext).encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        return None


def _connect():
    conn = sqlite3.connect(Config.DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            token_encrypted TEXT NOT NULL,
            client_name TEXT NOT NULL,
            telegram_id TEXT NOT NULL DEFAULT '',
            link_type TEXT NOT NULL CHECK(link_type IN ('temporary', 'permanent')),
            created_at INTEGER NOT NULL,
            activated_at INTEGER,
            expires_at INTEGER,
            last_used_at INTEGER,
            revoked_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_subscription_links_client
        ON subscription_links(client_name, telegram_id, revoked_at, created_at)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_clients (
            client_name TEXT PRIMARY KEY,
            default_link_type TEXT NOT NULL DEFAULT 'temporary'
                CHECK(default_link_type IN ('temporary', 'permanent')),
            enabled INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    client_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(subscription_clients)")
    }
    if "enabled" not in client_columns:
        conn.execute(
            "ALTER TABLE subscription_clients "
            "ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1"
        )
    conn.commit()
    return conn


def _row_token(row):
    if not row:
        return None
    token = _decrypt_token(row["token_encrypted"])
    if token and OPENVPN_SUBSCRIPTION_TOKEN_PATTERN.fullmatch(token):
        return token
    return None


def get_subscription_link_state(token, now=None):
    """Return the lifecycle state without granting access to the subscription."""
    token = (token or "").strip()
    if not OPENVPN_SUBSCRIPTION_TOKEN_PATTERN.fullmatch(token):
        return "invalid"
    current_time = int(time.time()) if now is None else int(now)
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT links.link_type, links.expires_at, links.revoked_at,
                   COALESCE(clients.enabled, 1) AS client_enabled
            FROM subscription_links AS links
            LEFT JOIN subscription_clients AS clients
              ON clients.client_name = links.client_name
            WHERE links.token_hash = ?
            """,
            (_token_hash(token),),
        ).fetchone()
    if not row:
        return "invalid"
    if row["revoked_at"] is not None:
        return "revoked"
    if not bool(row["client_enabled"]):
        return "revoked"
    if (
        row["link_type"] == "temporary"
        and row["expires_at"] is not None
        and current_time > row["expires_at"]
    ):
        return "expired"
    return "active"


def get_client_subscription_temporary(client_name):
    client_name = (client_name or "").strip()
    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return True
    with _connect() as conn:
        row = conn.execute(
            "SELECT default_link_type FROM subscription_clients WHERE client_name = ?",
            (client_name,),
        ).fetchone()
    return not row or row["default_link_type"] != "permanent"


def get_client_subscription_enabled(client_name):
    client_name = (client_name or "").strip()
    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return False
    with _connect() as conn:
        row = conn.execute(
            "SELECT enabled FROM subscription_clients WHERE client_name = ?",
            (client_name,),
        ).fetchone()
    return not row or bool(row["enabled"])


def set_client_subscription_enabled(client_name, enabled):
    client_name = (client_name or "").strip()
    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return None
    enabled = bool(enabled)
    now = int(time.time())
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO subscription_clients(client_name, enabled)
            VALUES (?, ?)
            ON CONFLICT(client_name) DO UPDATE SET enabled = excluded.enabled
            """,
            (client_name, int(enabled)),
        )
        if not enabled:
            conn.execute(
                """
                UPDATE subscription_links SET revoked_at = ?
                WHERE client_name = ? AND revoked_at IS NULL
                """,
                (now, client_name),
            )
        conn.commit()
    return enabled


def get_client_subscription_url(client_name):
    client_name = (client_name or "").strip()
    if (
        not CLIENT_NAME_PATTERN.fullmatch(client_name)
        or not are_subscriptions_active()
        or not get_client_subscription_enabled(client_name)
    ):
        return None
    _get_fernet()
    now = int(time.time())
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT token_encrypted FROM subscription_links
            WHERE client_name = ? AND telegram_id = '' AND revoked_at IS NULL
              AND (link_type = 'permanent' OR activated_at IS NULL OR expires_at >= ?)
            ORDER BY created_at DESC, id DESC LIMIT 1
            """,
            (client_name, now),
        ).fetchone()
    token = _row_token(row)
    if not token:
        return None
    return subscription_page_url(token) or None


def subscription_urls_by_client():
    if not are_subscriptions_active():
        return {}
    _get_fernet()
    now = int(time.time())
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT token_encrypted, client_name, created_at, id
            FROM subscription_links
            WHERE telegram_id = '' AND revoked_at IS NULL
              AND (link_type = 'permanent' OR activated_at IS NULL OR expires_at >= ?)
            ORDER BY created_at DESC, id DESC
            """,
            (now,),
        ).fetchall()
    enabled = get_subscription_enabled_map()
    best = {}
    for row in rows:
        name = row["client_name"]
        if not name or name in best or not enabled.get(name, True):
            continue
        token = _row_token(row)
        if token:
            best[name] = subscription_page_url(token) or ""
    return {name: url for name, url in best.items() if url}


def _telegram_clients_by_vpn_name(names):
    try:
        from src.tg_bot.admin import get_user_label
        from src.tg_bot.config import get_client_mapping
    except Exception:
        return {}
    result = {name: [] for name in names}
    for telegram_id, client_names in get_client_mapping().items():
        label = get_user_label(str(telegram_id))
        for client_name in client_names:
            if client_name not in result:
                continue
            if label not in result[client_name]:
                result[client_name].append(label)
    return result


def list_public_link_clients():
    from src.ui.services.openvpn_service import get_all_openvpn_clients
    from src.ui.utils.wireguard_naming import list_wireguard_client_names

    names = {}
    for name in get_all_openvpn_clients() or []:
        item = names.setdefault(name, {"name": name, "openvpn": False, "wireguard": False})
        item["openvpn"] = True
    for name in list_wireguard_client_names():
        item = names.setdefault(name, {"name": name, "openvpn": False, "wireguard": False})
        item["wireguard"] = True
    urls = subscription_urls_by_client()
    temporary = get_subscription_temporary_map()
    enabled = get_subscription_enabled_map()
    telegram_by_client = _telegram_clients_by_vpn_name(names)
    clients = []
    for item in names.values():
        item["url"] = urls.get(item["name"], "")
        item["public"] = bool(item["url"])
        item["disabled"] = not enabled.get(item["name"], True)
        item["temporary"] = temporary.get(item["name"], True)
        item["telegram"] = telegram_by_client.get(item["name"], [])
        clients.append(item)
    clients.sort(key=lambda item: item["name"].lower())
    return clients


def get_subscription_temporary_map():
    with _connect() as conn:
        rows = conn.execute(
            "SELECT client_name, default_link_type FROM subscription_clients"
        ).fetchall()
    return {
        row["client_name"]: row["default_link_type"] != "permanent"
        for row in rows
    }


def get_subscription_enabled_map():
    with _connect() as conn:
        rows = conn.execute(
            "SELECT client_name, enabled FROM subscription_clients"
        ).fetchall()
    return {row["client_name"]: bool(row["enabled"]) for row in rows}


def set_client_subscription_temporary(client_name, temporary):
    client_name = (client_name or "").strip()
    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return None
    set_clients_subscription_temporary({client_name: temporary})
    return bool(temporary)


def set_clients_subscription_temporary(client_modes):
    normalized = {
        (client_name or "").strip(): bool(temporary)
        for client_name, temporary in client_modes.items()
        if CLIENT_NAME_PATTERN.fullmatch((client_name or "").strip())
    }
    if not normalized:
        return
    now = int(time.time())
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for client_name, temporary in normalized.items():
            link_type = "temporary" if temporary else "permanent"
            row = conn.execute(
                "SELECT default_link_type FROM subscription_clients WHERE client_name = ?",
                (client_name,),
            ).fetchone()
            previous = row["default_link_type"] if row else "temporary"
            conn.execute(
                """
                INSERT INTO subscription_clients(client_name, default_link_type)
                VALUES (?, ?)
                ON CONFLICT(client_name) DO UPDATE SET
                    default_link_type = excluded.default_link_type
                """,
                (client_name, link_type),
            )
            if previous != link_type:
                conn.execute(
                    """
                    UPDATE subscription_links SET revoked_at = ?
                    WHERE client_name = ? AND revoked_at IS NULL
                    """,
                    (now, client_name),
                )
        conn.commit()


def _create_ticket(client_name, telegram_id=None, temporary=True):
    client_name = (client_name or "").strip()
    if (
        not CLIENT_NAME_PATTERN.fullmatch(client_name)
        or not get_client_subscription_enabled(client_name)
    ):
        return None
    now = int(time.time())
    telegram_id = _normalize_telegram_id(telegram_id) or ""
    temporary = bool(temporary)
    link_type = "temporary" if temporary else "permanent"
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if temporary:
            row = conn.execute(
                """
                SELECT id, token_encrypted FROM subscription_links
                WHERE client_name = ? AND telegram_id = ?
                  AND link_type = 'temporary' AND activated_at IS NULL
                  AND revoked_at IS NULL
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (client_name, telegram_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id, token_encrypted FROM subscription_links
                WHERE client_name = ? AND telegram_id = ?
                  AND link_type = 'permanent' AND revoked_at IS NULL
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (client_name, telegram_id),
            ).fetchone()
        existing = _row_token(row)
        if existing:
            conn.commit()
            return existing
        if row:
            # The encryption key may have been replaced after a restore.
            # Keep hash-based validation safe, but rotate a link whose URL
            # can no longer be recovered.
            conn.execute(
                "UPDATE subscription_links SET revoked_at = ? WHERE id = ?",
                (now, row["id"]),
            )
        for _ in range(8):
            token = secrets.token_urlsafe(24)
            if not OPENVPN_SUBSCRIPTION_TOKEN_PATTERN.fullmatch(token):
                continue
            try:
                conn.execute(
                    """
                    INSERT INTO subscription_links(
                        token_hash, token_encrypted, client_name, telegram_id,
                        link_type, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _token_hash(token),
                        _encrypt_token(token),
                        client_name,
                        telegram_id,
                        link_type,
                        now,
                    ),
                )
                conn.commit()
                return token
            except sqlite3.IntegrityError:
                continue
        conn.rollback()
    return None


def create_subscription_url(client_name, telegram_id=None):
    if not are_subscriptions_active():
        return None
    _get_fernet()
    temporary = get_client_subscription_temporary(client_name)
    token = _create_ticket(client_name, telegram_id=telegram_id, temporary=temporary)
    if not token:
        return None
    url = subscription_page_url(token)
    return url or None


def _log_subscription_opened(record):
    try:
        from src.tg_bot.audit import log_action

        link_kind = "temporary" if _is_temporary(record) else "permanent"
        log_action(
            "system",
            link_kind,
            "Система",
            "subscription_opened",
            record.get("client_name") or "",
        )
    except Exception:
        pass


def authorize_subscription_page(token, user_agent=None, method=None):
    token = (token or "").strip()
    if not OPENVPN_SUBSCRIPTION_TOKEN_PATTERN.fullmatch(token):
        return None
    preview = is_preview_request(user_agent, method)
    now = int(time.time())
    opened_now = False
    result = None
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM subscription_links WHERE token_hash = ? AND revoked_at IS NULL",
            (_token_hash(token),),
        ).fetchone()
        if not row:
            conn.rollback()
            return None
        client_settings = conn.execute(
            "SELECT enabled FROM subscription_clients WHERE client_name = ?",
            (row["client_name"],),
        ).fetchone()
        if client_settings and not bool(client_settings["enabled"]):
            conn.rollback()
            return None
        record = _record_from_row(row)
        if preview:
            conn.rollback()
            return record
        activated_at = row["activated_at"]
        if activated_at is None:
            expires_at = now + get_subscription_link_lifetime_seconds() if row["link_type"] == "temporary" else None
            conn.execute(
                """
                UPDATE subscription_links
                SET activated_at = ?, expires_at = ?, last_used_at = ?
                WHERE id = ?
                """,
                (now, expires_at, now, row["id"]),
            )
            opened_now = True
            record["opened_at"] = now
            record["expires_at"] = expires_at
            result = record
        elif row["link_type"] == "permanent":
            conn.execute(
                "UPDATE subscription_links SET last_used_at = ? WHERE id = ?",
                (now, row["id"]),
            )
            result = record
        elif row["expires_at"] is not None and now <= row["expires_at"]:
            conn.execute(
                "UPDATE subscription_links SET last_used_at = ? WHERE id = ?",
                (now, row["id"]),
            )
            result = record
        conn.commit()
    if opened_now:
        _log_subscription_opened(result)
    return result


def authorize_subscription_file(token, user_agent=None, method=None):
    token = (token or "").strip()
    if not OPENVPN_SUBSCRIPTION_TOKEN_PATTERN.fullmatch(token):
        return None
    if is_preview_request(user_agent, method):
        return None
    now = int(time.time())
    opened_now = False
    result = None
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM subscription_links WHERE token_hash = ? AND revoked_at IS NULL",
            (_token_hash(token),),
        ).fetchone()
        if not row:
            conn.rollback()
            return None
        client_settings = conn.execute(
            "SELECT enabled FROM subscription_clients WHERE client_name = ?",
            (row["client_name"],),
        ).fetchone()
        if client_settings and not bool(client_settings["enabled"]):
            conn.rollback()
            return None
        record = _record_from_row(row)
        activated_at = row["activated_at"]
        if activated_at is None:
            expires_at = now + get_subscription_link_lifetime_seconds() if row["link_type"] == "temporary" else None
            conn.execute(
                """
                UPDATE subscription_links
                SET activated_at = ?, expires_at = ?, last_used_at = ?
                WHERE id = ?
                """,
                (now, expires_at, now, row["id"]),
            )
            opened_now = True
            record["opened_at"] = now
            record["expires_at"] = expires_at
            result = record
        elif row["link_type"] == "permanent":
            conn.execute(
                "UPDATE subscription_links SET last_used_at = ? WHERE id = ?",
                (now, row["id"]),
            )
            result = record
        elif row["expires_at"] is not None and now <= row["expires_at"]:
            conn.execute(
                "UPDATE subscription_links SET last_used_at = ? WHERE id = ?",
                (now, row["id"]),
            )
            result = record
        conn.commit()
    if opened_now:
        _log_subscription_opened(result)
    return result


def _record_from_row(row):
    return {
        "client_name": row["client_name"],
        "created_at": float(row["created_at"]),
        "opened_at": float(row["activated_at"]) if row["activated_at"] is not None else None,
        "expires_at": float(row["expires_at"]) if row["expires_at"] is not None else None,
        "telegram_id": row["telegram_id"] or None,
        "temporary": row["link_type"] == "temporary",
    }


def revoke_client_subscription(client_name, preserve_preference=False):
    client_name = (client_name or "").strip()
    if not client_name:
        return 0
    now = int(time.time())
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """
            UPDATE subscription_links SET revoked_at = ?
            WHERE client_name = ? AND revoked_at IS NULL
            """,
            (now, client_name),
        )
        if not preserve_preference:
            conn.execute(
                "DELETE FROM subscription_clients WHERE client_name = ?",
                (client_name,),
            )
        conn.commit()
        return cursor.rowcount


_OPENVPN_PROFILE_FLAGS = {
    "vpn": "openvpn_vpn",
    "antizapret": "openvpn_antizapret",
}
_OPENVPN_TRANSPORT_FLAGS = {
    "auto": "openvpn_default",
    "tcp": "openvpn_tcp",
    "udp": "openvpn_udp",
}
_WIREGUARD_PROFILE_FLAGS = {
    "vpn": "wireguard_vpn",
    "antizapret": "wireguard_antizapret",
}
_WIREGUARD_KIND_FLAGS = {
    "wireguard": "wireguard_wg",
    "amnezia": "wireguard_am",
}

_SUBSCRIPTION_SERVICE_REQUIREMENTS = (
    (
        "openvpn",
        "openvpn-server@antizapret-tcp.service",
        "AntiZapret TCP",
        ("openvpn_antizapret", "openvpn_tcp"),
    ),
    (
        "openvpn",
        "openvpn-server@antizapret-udp.service",
        "AntiZapret UDP",
        ("openvpn_antizapret", "openvpn_udp"),
    ),
    (
        "openvpn",
        "openvpn-server@vpn-tcp.service",
        "VPN TCP",
        ("openvpn_vpn", "openvpn_tcp"),
    ),
    (
        "openvpn",
        "openvpn-server@vpn-udp.service",
        "VPN UDP",
        ("openvpn_vpn", "openvpn_udp"),
    ),
    (
        "wireguard",
        "wg-quick@antizapret.service",
        "WireGuard AntiZapret",
        ("wireguard_antizapret", "wireguard_wg"),
    ),
    (
        "wireguard",
        "wg-quick@antizapret.service",
        "WireGuard AntiZapret",
        ("wireguard_antizapret", "wireguard_am"),
    ),
    (
        "wireguard",
        "wg-quick@vpn.service",
        "WireGuard VPN",
        ("wireguard_vpn", "wireguard_wg"),
    ),
    (
        "wireguard",
        "wg-quick@vpn.service",
        "WireGuard VPN",
        ("wireguard_vpn", "wireguard_am"),
    ),
)


def get_subscription_service_warnings(
    protocols, *, has_openvpn=True, has_wireguard=True
):
    """Предупреждения о выбранных конфигурациях с неактивными VPN-службами."""
    from src.ui.services.system_info_service import get_system_info

    services = (get_system_info() or {}).get("vpn_services") or []
    states = {
        item.get("unit"): item.get("state", "unknown")
        for item in services
        if isinstance(item, dict) and item.get("unit")
    }
    warnings = []
    checked_units = set()
    available_families = {
        family
        for family, available in (
            ("openvpn", has_openvpn),
            ("wireguard", has_wireguard),
        )
        if available
    }
    for family, unit, label, required_flags in _SUBSCRIPTION_SERVICE_REQUIREMENTS:
        if (
            family not in available_families
            or unit in checked_units
            or not all(protocols.get(flag, False) for flag in required_flags)
        ):
            continue
        checked_units.add(unit)
        state = states.get(unit, "unknown")
        if state == "active":
            continue
        if state == "inactive":
            reason = "отключена"
        elif state == "not-found":
            reason = "не найдена"
        elif state == "failed":
            reason = "завершилась с ошибкой"
        else:
            warnings.append(
                f"Состояние службы {label} ({unit}) не определено ({state}). "
                f"Работоспособность конфигурации {label} не подтверждена."
            )
            continue
        warnings.append(
            f"Служба {label} ({unit}) {reason}. "
            f"Конфигурация {label} не будет работать."
        )
    return warnings


def _telegram_ids_for_client(client_name):
    try:
        from src.tg_bot.config import get_client_mapping
    except Exception:
        return []
    ids = []
    for telegram_id, names in get_client_mapping().items():
        if client_name in names:
            ids.append(str(telegram_id))
    return ids


def resolve_subscription_protocols(client_name, telegram_id=None):
    from src.ui.services.settings_service import get_vpn_client_protocols

    merged = get_vpn_client_protocols(client_name)
    try:
        from src.tg_bot.config import get_client_allowed_protocols
    except Exception:
        return merged
    tid = _normalize_telegram_id(telegram_id)
    ids = [tid] if tid else _telegram_ids_for_client(client_name)
    for other_id in ids:
        other = get_client_allowed_protocols(other_id)
        for key in list(merged):
            merged[key] = bool(merged.get(key, True)) and bool(other.get(key, True))
    return merged


def _item_allowed_by_protocols(item, protocols):
    if not protocols:
        return True
    family = item.get("family") or "openvpn"
    profile = item.get("profile")
    if family == "wireguard":
        profile_flag = _WIREGUARD_PROFILE_FLAGS.get(profile)
        if profile_flag and not protocols.get(profile_flag, True):
            return False
        if profile == "other" and not (
            protocols.get("wireguard_vpn", True)
            or protocols.get("wireguard_antizapret", True)
        ):
            return False
        kind_flag = _WIREGUARD_KIND_FLAGS.get(item.get("kind"))
        if kind_flag and not protocols.get(kind_flag, True):
            return False
        return True
    profile_flag = _OPENVPN_PROFILE_FLAGS.get(profile)
    if profile_flag and not protocols.get(profile_flag, True):
        return False
    if profile == "other" and not (
        protocols.get("openvpn_vpn", True) or protocols.get("openvpn_antizapret", True)
    ):
        return False
    protocol_flag = _OPENVPN_TRANSPORT_FLAGS.get(item.get("protocol"))
    if protocol_flag and not protocols.get(protocol_flag, True):
        return False
    return True


def public_profile_items(client_name, telegram_id=None):
    protocols = resolve_subscription_protocols(client_name, telegram_id)
    items = []
    for choice in list_openvpn_profile_choices(client_name):
        item = {
            "family": "openvpn",
            "slug": choice["slug"],
            "profile": choice["profile"],
            "protocol": choice["protocol"],
            "filename": choice["filename"],
            "label": choice["label"],
            "ext": "ovpn",
        }
        if _item_allowed_by_protocols(item, protocols):
            items.append(item)
    for choice in list_wireguard_profile_choices(client_name):
        item = {
            "family": "wireguard",
            "slug": choice["slug"],
            "profile": choice["profile"],
            "kind": choice["kind"],
            "filename": choice["filename"],
            "label": choice["label"],
            "ext": "conf",
        }
        if _item_allowed_by_protocols(item, protocols):
            items.append(item)
    return items


def resolve_subscription_file(client_name, slug, telegram_id=None):
    slug = (slug or "").strip().lower()
    if not OPENVPN_SUBSCRIPTION_SLUG_PATTERN.fullmatch(slug):
        return None
    protocols = resolve_subscription_protocols(client_name, telegram_id)
    for choice in list_openvpn_profile_choices(client_name):
        if choice["slug"] != slug:
            continue
        choice = dict(choice)
        choice["family"] = "openvpn"
        choice["ext"] = "ovpn"
        if not _item_allowed_by_protocols(choice, protocols):
            return None
        path = choice["path"]
        if os.path.isfile(path):
            return choice
        return None
    for choice in list_wireguard_profile_choices(client_name):
        if choice["slug"] != slug:
            continue
        if not _item_allowed_by_protocols(choice, protocols):
            return None
        path = choice["path"]
        if os.path.isfile(path):
            return choice
        return None
    return None


def subscription_display_name(client_name):
    return clean_client_display_name(client_name, get_external_ip()) or client_name


def _format_last_seen(value):
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("T", " ", 1).split("+")[0].split("Z")[0].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).strftime("%d.%m.%Y, %H:%M")
        except ValueError:
            continue
    return text


def _format_last_seen_dt(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y, %H:%M")
    return _format_last_seen(value)


def _usage_payload(traffic_bytes, last_seen):
    from src.ui.utils.format_utils import format_bytes

    return {
        "traffic_total": format_bytes(traffic_bytes) if traffic_bytes else "—",
        "last_seen": last_seen or "—",
    }


def _status_fields(kind):
    labels = {
        "blocked": "Заблокирован",
        "online": "В сети",
        "offline": "Не в сети",
        "expired": "Истекла",
        "expiring": "Скоро истечёт",
        "unknown": "—",
    }
    if kind not in labels:
        kind = "unknown"
    return {
        "status_label": labels[kind],
        "status_kind": kind,
    }


def _with_profile_status(payload, by_profile, default_profile="antizapret"):
    chosen = (
        by_profile.get(default_profile)
        or by_profile.get("vpn")
        or _status_fields("offline")
    )
    payload.update(chosen)
    payload["by_profile"] = by_profile
    return payload


def _empty_profile_status(kind="offline"):
    return {
        "antizapret": _status_fields(kind),
        "vpn": _status_fields(kind),
    }


def _openvpn_profile_of_protocol(protocol):
    proto = (protocol or "").strip().upper()
    if proto.startswith("VPN"):
        return "vpn"
    return "antizapret"


def _client_is_banned(client_name, variants):
    from src.ui.services.openvpn_service import read_banned_clients

    banned = read_banned_clients()
    if client_name in banned:
        return True
    return any(_client_name_matches(name, variants) for name in banned)


def _client_identity_variants(client_name):
    name = (client_name or "").strip().lower()
    if not name:
        return []
    variants = {name}
    without_note = re.sub(r"\s*\([^)]+\)\s*$", "", name).strip()
    if without_note:
        variants.add(without_note)
    return list(variants)


def _client_name_matches(value, variants):
    text = (value or "").strip().lower()
    if not text or text in ("n/a", "unknown"):
        return False
    if text in variants:
        return True
    for item in variants:
        if text.startswith(item + " (") or text.startswith(item + "@"):
            return True
    return False


def _openvpn_usage(variants, banned=False, renew_state=None):
    from src.config import Config
    from src.openvpn_status import OPENVPN_STATUS_SOURCES
    from src.ui.services.openvpn_service import read_csv

    if banned:
        by_profile = _empty_profile_status("blocked")
    elif renew_state == "expired":
        by_profile = _empty_profile_status("expired")
    else:
        by_profile = _empty_profile_status("offline")

    if not variants:
        return _with_profile_status(_usage_payload(0, ""), by_profile)

    equals = " OR ".join(["lower(client_name) = ?"] * len(variants))
    likes = " OR ".join(["lower(client_name) LIKE ?"] * len(variants))
    params = list(variants) + [item + " (%" for item in variants]
    traffic = 0
    last_seen = ""
    try:
        with sqlite3.connect(Config.LOGS_DATABASE_PATH) as conn:
            row = conn.execute(
                f"""SELECT COALESCE(SUM(bytes_received), 0),
                           COALESCE(SUM(bytes_sent), 0),
                           MAX(connected_since)
                    FROM connection_logs
                    WHERE {equals} OR {likes}""",
                params,
            ).fetchone()
        if row:
            traffic = int(row[0] or 0) + int(row[1] or 0)
            last_seen = _format_last_seen(row[2])
    except (OSError, sqlite3.Error):
        pass

    if not banned and renew_state != "expired":
        online_profiles = set()
        try:
            for protocol, files, _ in OPENVPN_STATUS_SOURCES:
                rows, _, _, error = read_csv(files[0], protocol)
                if error:
                    continue
                for row in rows or []:
                    name = row[0] if row else ""
                    if name and name != "UNDEF" and _client_name_matches(name, variants):
                        online_profiles.add(_openvpn_profile_of_protocol(protocol))
        except Exception:
            pass
        for profile in ("antizapret", "vpn"):
            if profile in online_profiles:
                by_profile[profile] = _status_fields("online")

    return _with_profile_status(_usage_payload(traffic, last_seen), by_profile)


def _wireguard_usage(variants):
    from src.config import Config
    from src.ui.services.wireguard_service import (
        get_disabled_wg_peers,
        get_wireguard_stats,
        parse_wireguard_output,
    )
    from src.ui.utils.time_utils import parse_relative_time

    by_profile = _empty_profile_status("offline")
    if not variants:
        return _with_profile_status(_usage_payload(0, ""), by_profile)

    traffic = 0
    try:
        with sqlite3.connect(Config.WG_STATS_PATH) as conn:
            rows = conn.execute(
                """SELECT client, total_received, total_sent, interface
                   FROM wg_total_stats"""
            ).fetchall()
        for client, received, sent, interface in rows:
            if str(interface or "").strip().lower().startswith("warp"):
                continue
            if not _client_name_matches(client, variants):
                continue
            traffic += int(received or 0) + int(sent or 0)
    except (OSError, sqlite3.Error):
        pass

    last_seen_dt = None
    online_profiles = set()
    try:
        stats = parse_wireguard_output(get_wireguard_stats(), hide_warp=True)
        for iface in stats or []:
            iface_name = str(iface.get("interface") or "").strip().lower()
            if iface_name not in ("vpn", "antizapret"):
                continue
            for peer in iface.get("peers") or []:
                if not _client_name_matches(peer.get("client"), variants):
                    continue
                if peer.get("online"):
                    online_profiles.add(iface_name)
                handshake = str(peer.get("latest_handshake") or "").strip()
                if not handshake:
                    continue
                if handshake.lower() == "now":
                    seen_dt = datetime.now()
                else:
                    try:
                        seen_dt = parse_relative_time(handshake)
                    except (TypeError, ValueError):
                        continue
                if last_seen_dt is None or seen_dt > last_seen_dt:
                    last_seen_dt = seen_dt
    except Exception:
        pass

    blocked_profiles = set()
    try:
        disabled = get_disabled_wg_peers()
        for iface_name, peers in (disabled or {}).items():
            profile = str(iface_name or "").strip().lower()
            if profile not in ("vpn", "antizapret"):
                continue
            for peer in peers or []:
                if _client_name_matches(peer.get("client"), variants):
                    blocked_profiles.add(profile)
                    break
    except Exception:
        pass

    for profile in ("antizapret", "vpn"):
        if profile in blocked_profiles:
            by_profile[profile] = _status_fields("blocked")
        elif profile in online_profiles:
            by_profile[profile] = _status_fields("online")
        else:
            by_profile[profile] = _status_fields("offline")

    return _with_profile_status(
        _usage_payload(traffic, _format_last_seen_dt(last_seen_dt)),
        by_profile,
    )


def subscription_client_summary(client_name):
    from src.ui.services.openvpn_service import (
        cert_days_left_fields,
        get_openvpn_cert_renew_state,
        get_openvpn_client_cert_expiry,
    )

    expiry_dt, expiry_label = get_openvpn_client_cert_expiry(client_name)
    days_left, days_label = cert_days_left_fields(expiry_dt)
    renew_state = get_openvpn_cert_renew_state(expiry_dt)
    variants = _client_identity_variants(client_name)
    banned = _client_is_banned(client_name, variants)

    if days_left is not None and days_left >= 1000:
        days_display = "∞"
        expiry_display = "Бессрочно"
    else:
        days_display = days_label
        expiry_display = expiry_label

    openvpn = _openvpn_usage(variants, banned=banned, renew_state=renew_state)
    wireguard = _wireguard_usage(variants)
    return {
        "days_label": days_display,
        "expiry_label": expiry_display,
        "status_label": openvpn.get("status_label") or "—",
        "status_kind": openvpn.get("status_kind") or "unknown",
        "openvpn": openvpn,
        "wireguard": wireguard,
        "last_seen": openvpn.get("last_seen") or "—",
        "traffic_total": openvpn.get("traffic_total") or "—",
    }
