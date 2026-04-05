import base64
import csv
import hashlib
import secrets
import sqlite3
import requests
import os
import platform
import re
import threading
import random
import time
import string
import psutil
import socket
import subprocess
import shutil
import json

from statistics import mean
from threading import Lock
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
    abort,
    make_response,
    render_template,
    send_file,
    url_for,
    redirect,
    request,
    jsonify,
    session,
)

from src.forms import LoginForm
from src.config import Config
from src.tg_bot.audit import log_action, get_logs, get_logs_count
from flask_bcrypt import Bcrypt
from datetime import date, datetime, timezone, timedelta
from zoneinfo._common import ZoneInfoNotFoundError
from collections import defaultdict

from cryptography import x509
from cryptography.hazmat.backends import default_backend

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


def _host_static_info():
    os_label = ""
    try:
        rel = platform.freedesktop_os_release()
        os_label = (
            rel.get("PRETTY_NAME")
            or f"{rel.get('NAME', 'Linux')} {rel.get('VERSION', '')}".strip()
        )
    except (OSError, AttributeError):
        os_label = f"{platform.system()} {platform.release()}".strip()
    physical = psutil.cpu_count(logical=False)
    logical = psutil.cpu_count(logical=True)
    cpu_cores = physical if physical else (logical or 1)
    return {"os_label": os_label, "cpu_cores": cpu_cores}


HOST_STATIC_INFO = _host_static_info()

# Службы VPN
VPN_SYSTEMD_UNITS = (
    ("openvpn-server@antizapret-udp.service", "Antizapret UDP", "openvpn"),
    ("openvpn-server@antizapret-tcp.service", "Antizapret TCP", "openvpn"),
    ("openvpn-server@vpn-udp.service", "VPN UDP", "openvpn"),
    ("openvpn-server@vpn-tcp.service", "VPN TCP", "openvpn"),
    ("wg-quick@antizapret.service", "Antizapret", "wireguard"),
    ("wg-quick@vpn.service", "VPN", "wireguard"),
)


def get_vpn_systemd_states():
    """Состояние ActiveState через systemctl is-active для каждого unit."""
    rows = []
    for unit, label, kind in VPN_SYSTEMD_UNITS:
        state = "unknown"
        try:
            completed = subprocess.run(
                ["/bin/systemctl", "is-active", unit],
                capture_output=True,
                text=True,
                timeout=8,
            )
            st = (completed.stdout or "").strip()
            if st:
                state = st
            else:
                load = subprocess.run(
                    ["/bin/systemctl", "show", "-p", "LoadState", "--value", unit],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                if (load.stdout or "").strip() == "not-found":
                    state = "not-found"
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            state = "unknown"
        rows.append(
            {
                "unit": unit,
                "label": label,
                "kind": kind,
                "state": state,
            }
        )
    return rows


VPN_SYSTEMD_UNIT_SET = frozenset(u[0] for u in VPN_SYSTEMD_UNITS)


def restart_vpn_systemd_unit(unit: str) -> tuple[bool, str]:
    """Перезапуск unit из белого списка VPN. Возвращает (успех по коду systemctl, сообщение)."""
    if unit not in VPN_SYSTEMD_UNIT_SET:
        return False, "unknown unit"
    try:
        completed = subprocess.run(
            ["/bin/systemctl", "restart", unit],
            capture_output=True,
            text=True,
            timeout=120,
        )
        err = (completed.stderr or completed.stdout or "").strip()
        if completed.returncode != 0:
            return False, err[:500] if err else "systemctl restart failed"
        return True, "ok"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return False, str(e)


SAMPLE_INTERVAL = 10  # текущая частота сбора
MAX_HISTORY_SECONDS = 7 * 24 * 3600  # сколько секунд хранить в памяти
LIVE_POINTS = 60
last_collect = 0
BOT_RESTART_LOCK = Lock()
BOT_SERVICE_NAME = "telegram-bot"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ANTIZAPRET_SETUP_PATH = "/root/antizapret/setup"
STATUSOPENVPN_SETUP_PATH = os.path.join(BASE_DIR, "setup")
ENV_PATH = os.path.join(BASE_DIR, "src", ".env")
SETTINGS_PATH = os.path.join(BASE_DIR, "src", "settings.json")
SETUP_DESCRIPTIONS_PATH = os.path.join(BASE_DIR, "src", "setup_descriptions.json")
LEGACY_ADMIN_INFO_PATH = os.path.join(BASE_DIR, "src", "telegram_admins.json")
CLIENT_MAPPING_KEY = "CLIENT_MAPPING"
OPENVPN_BANNED_CLIENTS_FILE = "/etc/openvpn/server/banned_clients"
OPENVPN_CLIENT_CONNECT_SCRIPT = "/etc/openvpn/server/scripts/client-connect.sh"
CLIENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")
CLIENT_SH_PATH = "/root/antizapret/client.sh"

OPENVPN_CONFIG_PATHS = [
    "/root/antizapret/client/openvpn/antizapret",
    "/root/antizapret/client/openvpn/antizapret-udp",
    "/root/antizapret/client/openvpn/antizapret-tcp",
    "/root/antizapret/client/openvpn/antizapret-udp-only",
    "/root/antizapret/client/openvpn/antizapret-tcp-only",
    "/root/antizapret/client/openvpn/vpn",
    "/root/antizapret/client/openvpn/vpn-tcp",
    "/root/antizapret/client/openvpn/vpn-udp",
]

OPENVPN_KEYS_DIR = "/etc/openvpn/client/keys"
OPENVPN_KEYS_DISABLED_DIR = os.path.join(OPENVPN_KEYS_DIR, "disabled")

CLIENT_CONNECT_BAN_CHECK_BLOCK = (
    'BANNED="/etc/openvpn/server/banned_clients"\n\n'
    'if [ -f "$BANNED" ]; then\n'
    '    if grep -q "^$common_name$" "$BANNED"; then\n'
    '        echo "Client $common_name banned" >&2\n'
    "        exit 1\n"
    "    fi\n"
    "fi\n"
)

OPENVPN_SOCKETS = {
    "antizapret-udp": "/run/openvpn-server/antizapret-udp.sock",
    "antizapret-tcp": "/run/openvpn-server/antizapret-tcp.sock",
    "vpn-udp": "/run/openvpn-server/vpn-udp.sock",
    "vpn-tcp": "/run/openvpn-server/vpn-tcp.sock",
}

PROTOCOL_TO_SOCKET = {
    "UDP": "antizapret-udp",
    "TCP": "antizapret-tcp",
    "VPN-UDP": "vpn-udp",
    "VPN-TCP": "vpn-tcp",
}


def read_env_values():
    values = {}
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except FileNotFoundError:
        return values
    return values


def read_setup_key_value_file(path):
    """Читает строки KEY=VALUE из файла установки. Возвращает (список пар, ошибка)."""
    pairs = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                pairs.append((key.strip(), value.strip()))
    except FileNotFoundError:
        return [], "not_found"
    except OSError as e:
        return [], str(e)
    return pairs, None


def _load_setup_descriptions():
    with open(SETUP_DESCRIPTIONS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["web_setup"], data["antizapret_setup"]


WEB_SETUP_DESCRIPTIONS, ANTIZAPRET_SETUP_DESCRIPTIONS = _load_setup_descriptions()


def can_start_bot(env_values=None):
    if env_values is None:
        env_values = read_env_values()
    bot_token = (env_values.get("BOT_TOKEN") or "").strip()
    admin_id = (env_values.get("ADMIN_ID") or "").strip()
    return bool(bot_token) and bool(parse_admin_ids(admin_id))


def update_env_values(updates):
    updates = {key: value for key, value in updates.items() if key}
    if not updates:
        return

    updated_keys = set()
    lines = []
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as env_file:
            lines = env_file.readlines()
    except FileNotFoundError:
        lines = []

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        key, _ = line.split("=", 1)
        key = key.strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}\n")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as env_file:
        env_file.writelines(new_lines)


DEFAULT_SETTINGS = {
    "app_name": "StatusOpenVPN",
    "telegram_admins": {},
    "bot_enabled": False,
    "hide_ovpn_ip": True,
    "hide_wg_ip": True,
    "stats_retention_days": 365,
}

MONTH_OPTIONS_RU = [
    (1, "Январь"),
    (2, "Февраль"),
    (3, "Март"),
    (4, "Апрель"),
    (5, "Май"),
    (6, "Июнь"),
    (7, "Июль"),
    (8, "Август"),
    (9, "Сентябрь"),
    (10, "Октябрь"),
    (11, "Ноябрь"),
    (12, "Декабрь"),
]


def write_settings_data(settings_data):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as settings_file:
        json.dump(settings_data, settings_file, ensure_ascii=False, indent=4)
        settings_file.write("\n")


def read_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as settings_file:
            data = json.load(settings_file)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    if not isinstance(data, dict):
        data = {}

    merged = DEFAULT_SETTINGS.copy()
    merged.update(data)

    telegram_admins = merged.get("telegram_admins")
    if not isinstance(telegram_admins, dict):
        telegram_admins = {}
        merged["telegram_admins"] = telegram_admins

    if not telegram_admins and os.path.exists(LEGACY_ADMIN_INFO_PATH):
        try:
            with open(LEGACY_ADMIN_INFO_PATH, "r", encoding="utf-8") as legacy_file:
                legacy_data = json.load(legacy_file)
            if isinstance(legacy_data, dict):
                merged["telegram_admins"] = legacy_data
                write_settings_data(merged)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    return merged


def write_settings(updated_settings):
    current_settings = read_settings()
    current_settings.update(updated_settings)
    write_settings_data(current_settings)


def parse_stats_retention_days(raw_value):
    try:
        days = int(str(raw_value).strip())
    except (TypeError, ValueError):
        return 365
    return max(30, min(days, 3650))


def get_stats_retention_days():
    return parse_stats_retention_days(read_settings().get("stats_retention_days", 365))


def get_available_stat_years(db_path, table_name, date_column):
    years = []
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT substr({date_column}, 1, 4) AS y
                FROM {table_name}
                WHERE substr({date_column}, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
                ORDER BY y DESC
                """
            ).fetchall()
            years = [int(row[0]) for row in rows if row and row[0].isdigit()]
    except sqlite3.Error:
        years = []

    current_year = datetime.now().year
    if current_year not in years:
        years.append(current_year)
    years = sorted(set(years), reverse=True)
    return years


def parse_date_yyyy_mm_dd(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def read_admin_info():
    data = read_settings().get("telegram_admins", {})
    if not isinstance(data, dict):
        return {}
    return data


def parse_admin_ids(admin_id_value):
    placeholder = "<Enter your user ID>"
    admin_ids = []
    for item in admin_id_value.split(","):
        item = item.strip()
        if not item:
            continue
        if item == placeholder:
            continue
        admin_ids.append(item)
    return admin_ids


def format_admin_ids(admin_ids):
    return ",".join(admin_ids)


def format_admin_display(admin_id, admin_info):
    info = admin_info.get(admin_id, {})
    display_name = (info.get("display_name") or "").strip()
    username = (info.get("username") or "").strip()

    if display_name and username:
        return f"{display_name} (@{username})"
    if display_name:
        return display_name
    if username:
        return f"@{username}"
    return f"ID: {admin_id}"


def build_admin_display_list(admin_id_value, admin_info):
    admin_ids = parse_admin_ids(admin_id_value)
    return [
        {"id": admin_id, "display": format_admin_display(admin_id, admin_info)}
        for admin_id in admin_ids
    ]


def _read_banned_clients():
    banned = set()
    try:
        with open(OPENVPN_BANNED_CLIENTS_FILE, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                banned.add(line)
    except FileNotFoundError:
        return set()
    return banned


def _write_banned_clients(clients):
    ordered = sorted(set(clients), key=str.lower)
    with open(OPENVPN_BANNED_CLIENTS_FILE, "w", encoding="utf-8") as f:
        if ordered:
            f.write("\n".join(ordered) + "\n")


def _ensure_client_connect_ban_check_block():
    try:
        with open(OPENVPN_CLIENT_CONNECT_SCRIPT, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = ""

    if CLIENT_CONNECT_BAN_CHECK_BLOCK in content:
        return

    if content.startswith("#!"):
        first_line_end = content.find("\n")
        if first_line_end == -1:
            shebang_line = content + "\n"
            rest = ""
        else:
            shebang_line = content[: first_line_end + 1]
            rest = content[first_line_end + 1 :]
        new_content = (
            shebang_line
            + "\n"
            + CLIENT_CONNECT_BAN_CHECK_BLOCK
            + "\n"
            + rest.lstrip("\n")
        )
    else:
        new_content = CLIENT_CONNECT_BAN_CHECK_BLOCK + "\n" + content.lstrip("\n")

    with open(OPENVPN_CLIENT_CONNECT_SCRIPT, "w", encoding="utf-8") as f:
        f.write(new_content)


def _extract_client_name_from_ovpn(filename):
    name = os.path.splitext(filename)[0]
    suffixes = ["-udp", "-tcp", "-udp-only", "-tcp-only"]
    for suffix in suffixes:
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break

    lowered = name.lower()
    for prefix in ("antizapret-", "vpn-"):
        if lowered.startswith(prefix):
            name = name[len(prefix) :]
            break

    return name.strip() or None


_OVPN_FILE_STEM_CORE = re.compile(
    r"^(?:antizapret|vpn)-(?:udp|tcp|udp-only|tcp-only)-(.+)-\([^)]+\)$",
    re.IGNORECASE,
)
_OVPN_FILE_STEM_SIMPLE = re.compile(
    r"^(?:antizapret|vpn)-(?:udp|tcp|udp-only|tcp-only)-(.+)$",
    re.IGNORECASE,
)


def _openvpn_client_identity_variants(name):
    """Варианты строки имени клиента (логи, CN, короткое имя) для сопоставления с файлом."""
    if not name:
        return set()
    n = name.strip()
    out = {n, n.lower()}
    no_ip = re.sub(r"\s*\([^)]*\)\s*$", "", n).strip()
    if no_ip:
        out.add(no_ip)
        out.add(no_ip.lower())
    c = n
    for _ in range(8):
        low = c.lower()
        if low.startswith("antizapret-"):
            c = c[11:]
        elif low.startswith("vpn-"):
            c = c[4:]
        else:
            break
        out.add(c)
        out.add(c.lower())
        no_ip2 = re.sub(r"\s*\([^)]*\)\s*$", "", c).strip()
        if no_ip2:
            out.add(no_ip2)
            out.add(no_ip2.lower())
    # vpn-udp-user → user (как в имени файла vpn-udp-user-(ip).ovpn)
    for _ in range(4):
        added = False
        for x in list(out):
            low = x.lower()
            for p in ("udp-", "tcp-", "udp-only-", "tcp-only-"):
                if low.startswith(p):
                    x2 = x[len(p) :].strip()
                    if x2 and x2 not in out:
                        out.add(x2)
                        out.add(x2.lower())
                        added = True
        if not added:
            break
    return {x for x in out if x}


def _openvpn_filename_identity_variants(stem):
    """Варианты идентификатора из имени файла без расширения."""
    if not stem:
        return set()
    out = {stem, stem.lower()}
    legacy = _extract_client_name_from_ovpn(stem + ".ovpn")
    if legacy:
        out.add(legacy)
        out.add(legacy.lower())
    m = _OVPN_FILE_STEM_CORE.match(stem)
    if m:
        g = m.group(1).strip()
        out.add(g)
        out.add(g.lower())
    else:
        m2 = _OVPN_FILE_STEM_SIMPLE.match(stem)
        if m2:
            g = m2.group(1).strip()
            out.add(g)
            out.add(g.lower())
    # vpn-user-(ip) / antizapret-user-(ip) в каталогах vpn/ и antizapret/
    m3 = re.match(r"^(?:antizapret|vpn)-(.+)-\([^)]+\)$", stem, re.IGNORECASE)
    if m3:
        g = m3.group(1).strip()
        out.add(g)
        out.add(g.lower())
    return {x for x in out if x}


def _openvpn_client_name_matches_ovpn_file(client_name, filename):
    """Имя клиента из UI совпадает с .ovpn (полный CN, короткое имя, как в tg cleanup_openvpn_files)."""
    if not filename.endswith(".ovpn"):
        return False
    stem = os.path.splitext(filename)[0]
    ca = _openvpn_client_identity_variants(client_name)
    fb = _openvpn_filename_identity_variants(stem)
    if ca & fb:
        return True
    cal = {x.lower() for x in ca}
    fbl = {x.lower() for x in fb}
    if cal & fbl:
        return True
    clean = (client_name or "").replace("antizapret-", "").replace("vpn-", "")
    if len(clean) >= 3 and clean in stem:
        return True
    return False


def _list_openvpn_ovpn_paths_for_client(client_name):
    """Пути к .ovpn файлам клиента (имя из логов/скрипта и имя файла могут отличаться)."""
    clean = (client_name or "").strip()
    if not clean:
        return []
    matches = []
    for base_dir in OPENVPN_CONFIG_PATHS:
        if not os.path.isdir(base_dir):
            continue
        for root, _, files in os.walk(base_dir):
            for filename in files:
                if not filename.endswith(".ovpn"):
                    continue
                if _openvpn_client_name_matches_ovpn_file(clean, filename):
                    matches.append(os.path.join(root, filename))
    matches.sort()
    return matches


def _ovpn_profile_label(full_path):
    """Краткая подпись профиля для UI."""
    basename = os.path.basename(full_path)
    parent = os.path.basename(os.path.dirname(full_path))
    if parent:
        return f"{basename} ({parent})"
    return basename


WG_CLIENT_CONFIG_DIRS = [
    ("/root/antizapret/client/wireguard/vpn", "vpn", "wg"),
    ("/root/antizapret/client/wireguard/antizapret", "antizapret", "wg"),
    ("/root/antizapret/client/amneziawg/vpn", "vpn", "am"),
    ("/root/antizapret/client/amneziawg/antizapret", "antizapret", "am"),
]


def _wg_conf_name_core(client_name: str) -> str:
    return (client_name or "").strip().replace("antizapret-", "").replace("vpn-", "")


def _wg_client_name_param_ok(name: str) -> bool:
    """Имя клиента из UI/запроса: без path traversal, до 128 символов (не только ASCII)."""
    raw = (name or "").strip()
    if not raw or len(raw) > 128:
        return False
    if "\x00" in raw or "/" in raw or "\\" in raw:
        return False
    return True


def _list_wg_conf_paths_for_client(client_name: str):
    """Пути к .conf клиента (шаблон интерфейс-имя-(…)-wg|am.conf)."""
    raw = (client_name or "").strip()
    if not raw or not _wg_client_name_param_ok(raw):
        return []
    name_core = _wg_conf_name_core(raw)
    if not name_core:
        return []
    matches = []
    for dir_path, iface, suffix in WG_CLIENT_CONFIG_DIRS:
        if not os.path.isdir(dir_path):
            continue
        pat = re.compile(
            rf"^{re.escape(iface)}-{re.escape(name_core)}-\([^)]+\)-{re.escape(suffix)}\.conf$"
        )
        try:
            for fn in os.listdir(dir_path):
                if pat.match(fn):
                    matches.append(os.path.join(dir_path, fn))
        except OSError:
            continue
    matches.sort()
    return matches


def _wg_conf_profile_label(full_path: str) -> str:
    basename = os.path.basename(full_path)
    parent = os.path.basename(os.path.dirname(full_path))
    if "amneziawg" in full_path:
        kind = "AmneziaWG"
    else:
        kind = "WireGuard"
    return f"{parent} · {kind} · {basename}"


def _wg_conf_path_is_allowed(abs_path: str) -> bool:
    abs_path = os.path.realpath(abs_path)
    roots = [
        os.path.realpath("/root/antizapret/client/wireguard"),
        os.path.realpath("/root/antizapret/client/amneziawg"),
    ]
    for root in roots:
        if abs_path.startswith(root + os.sep) and abs_path.endswith(".conf"):
            return os.path.isfile(abs_path)
    return False


def clean_client_display_name(client_name, server_ip):
    if not client_name:
        return client_name

    if not server_ip or not isinstance(server_ip, str):
        return client_name

    ip_pattern = re.escape(server_ip)
    client_name = re.sub(
        rf"[\s@\-\(\[]*{ip_pattern}(?::\d+)?[\)\]]*",
        "",
        client_name,
    )

    return client_name.strip()


def get_all_openvpn_clients():
    if not os.path.exists(CLIENT_SH_PATH):
        clients = set()
        for base_dir in OPENVPN_CONFIG_PATHS:
            if not os.path.exists(base_dir):
                continue
            for root, _, files in os.walk(base_dir):
                for filename in files:
                    if not filename.endswith(".ovpn"):
                        continue
                    client_name = _extract_client_name_from_ovpn(filename)
                    if client_name:
                        clients.add(client_name)
        return clients

    try:
        env = os.environ.copy()
        env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        proc = subprocess.run(
            [CLIENT_SH_PATH, "3"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
    except Exception:
        return set()

    if proc.returncode != 0:
        return set()

    clients = set()
    for raw in (proc.stdout or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("OpenVPN client names:") or line.startswith(
            "OpenVPN - List clients"
        ):
            continue
        clients.add(line)
    return clients


def _list_openvpn_client_crt_files(client_name):
    """Пути к .crt клиента в активной и отключённой директориях."""
    paths = []
    clean = (client_name or "").strip()
    if not clean:
        return paths
    for base in (OPENVPN_KEYS_DIR, OPENVPN_KEYS_DISABLED_DIR):
        if not os.path.isdir(base):
            continue
        try:
            for filename in os.listdir(base):
                if not filename.endswith(".crt"):
                    continue
                if clean in filename:
                    paths.append(os.path.join(base, filename))
        except OSError:
            continue
    return paths


def _read_pem_cert_not_after_utc(path):
    """Читает дату окончания действия сертификата (UTC, naive)."""
    try:
        with open(path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())
        na = getattr(cert, "not_valid_after_utc", None)
        if na is not None:
            na = na.replace(tzinfo=None)
        else:
            na = cert.not_valid_after
        return na
    except Exception:
        return None


def _get_openvpn_client_cert_expiry(client_name):
    """По всем .crt клиента возвращает минимальный срок (самый ранний) и подпись для UI."""
    paths = _list_openvpn_client_crt_files(client_name)
    if not paths:
        return None, "—"
    earliest = None
    for path in paths:
        na = _read_pem_cert_not_after_utc(path)
        if na is None:
            continue
        if earliest is None or na < earliest:
            earliest = na
    if earliest is None:
        return None, "—"
    return earliest, earliest.strftime("%d.%m.%Y")


def _cert_days_left_fields(expiry_dt):
    """Подпись остатка до окончания сертификата: дни (≥1 суток) или часы и минуты (<1 суток)."""
    if expiry_dt is None:
        return None, "—"
    total = (expiry_dt - datetime.utcnow()).total_seconds()
    if total > 0:
        if total < 86400:
            h = int(total // 3600)
            m = int((total % 3600) // 60)
            if h == 0 and m == 0:
                return None, "< 1 мин"
            return None, f"{h} ч {m} мин"
        d = int(total // 86400)
        return d, f"{d} дн."
    tv = -total
    if tv >= 86400:
        d = int(tv // 86400)
        return -d, "срок истек"
    h = int(tv // 3600)
    m = int((tv % 3600) // 60)
    if h > 0:
        return None, "срок истек"
    if m > 0:
        return None, "срок истек"
    return None, "срок истек"


def send_openvpn_command(socket_name, command, timeout=5):
    socket_path = OPENVPN_SOCKETS.get(socket_name)
    if not socket_path:
        return None, f"Unknown socket: {socket_name}"

    if not os.path.exists(socket_path):
        return None, f"Socket not found: {socket_path}"

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(socket_path)

        sock.recv(4096)

        sock.sendall((command + "\n").encode())

        response = b""
        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
                if b"END" in chunk or b"SUCCESS" in chunk or b"ERROR" in chunk:
                    break
            except socket.timeout:
                break

        sock.close()
        return response.decode("utf-8", errors="replace"), None

    except socket.error as e:
        return None, f"Socket error: {str(e)}"
    except Exception as e:
        return None, f"Error: {str(e)}"


def get_openvpn_clients_from_socket(protocol):
    socket_name = PROTOCOL_TO_SOCKET.get(protocol)
    if not socket_name:
        return [], f"Unknown protocol: {protocol}"

    response, error = send_openvpn_command(socket_name, "status 2")
    if error:
        return [], error

    clients = []
    for line in response.split("\n"):
        line = line.strip()

        if line.startswith("CLIENT_LIST"):
            parts = line.split(",")
            if len(parts) >= 11:
                clients.append(
                    {
                        "common_name": parts[1],
                        "real_address": parts[2],
                        "virtual_address": parts[3],
                        "bytes_received": int(parts[5]) if parts[5].isdigit() else 0,
                        "bytes_sent": int(parts[6]) if parts[6].isdigit() else 0,
                        "connected_since": parts[7],
                        "client_id": parts[10] if len(parts) > 10 else None,
                    }
                )

    return clients, None


def kick_openvpn_client(client_name, protocol=None):
    protocols_to_check = (
        [protocol] if protocol else ["UDP", "TCP", "VPN-UDP", "VPN-TCP"]
    )
    kicked = False
    errors = []

    for proto in protocols_to_check:
        clients, error = get_openvpn_clients_from_socket(proto)
        if error:
            errors.append(f"{proto}: {error}")
            continue

        for client in clients:
            if client["common_name"] == client_name:
                socket_name = PROTOCOL_TO_SOCKET.get(proto)
                if client.get("client_id"):
                    cmd = f"client-kill {client['client_id']}"
                else:
                    cmd = f"kill {client_name}"

                response, err = send_openvpn_command(socket_name, cmd)
                if err:
                    errors.append(f"{proto}: {err}")
                elif response and "SUCCESS" in response:
                    kicked = True
                else:
                    errors.append(f"{proto}: Unexpected response: {response}")

    return kicked, errors


def parse_client_mapping(env_values):
    raw_value = (env_values.get(CLIENT_MAPPING_KEY) or "").strip()
    if not raw_value:
        return {}
    mapping = {}
    for item in raw_value.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        telegram_id, client_name = item.split(":", 1)
        telegram_id = telegram_id.strip()
        client_name = client_name.strip()
        if not telegram_id or not client_name:
            continue
        mapping[telegram_id] = client_name
    return mapping


def build_client_mapping_list(env_values, admin_info):
    mapping = parse_client_mapping(env_values)
    mapping_list = []
    for telegram_id, client_name in mapping.items():
        display = format_admin_display(telegram_id, admin_info)
        mapping_list.append(
            {
                "telegram_id": telegram_id,
                "display": display,
                "client_name": client_name,
            }
        )
    mapping_list.sort(key=lambda item: item["client_name"].lower())
    return mapping_list


def build_available_admin_candidates(admin_info, admin_ids):
    available = []
    admin_id_set = set(admin_ids)
    for admin_id in admin_info.keys():
        if admin_id in admin_id_set:
            continue
        available.append(
            {"id": admin_id, "display": format_admin_display(admin_id, admin_info)}
        )
    available.sort(key=lambda item: item["display"].lower())
    return available


def restart_telegram_bot():
    with BOT_RESTART_LOCK:
        if not os.path.exists("/etc/systemd/system/telegram-bot.service"):
            return False, "Служба telegram-bot не создана"
        try:
            subprocess.run(
                ["/bin/systemctl", "restart", BOT_SERVICE_NAME],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return True, None
        except subprocess.CalledProcessError as exc:
            try:
                subprocess.run(
                    ["/bin/systemctl", "reset-failed", f"{BOT_SERVICE_NAME}.service"],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except Exception:
                pass
            return False, exc.stderr.strip() or "неизвестная ошибка"


def stop_telegram_bot():
    with BOT_RESTART_LOCK:
        if not os.path.exists("/etc/systemd/system/telegram-bot.service"):
            return False, "Служба telegram-bot не создана"
        try:
            subprocess.run(
                ["/bin/systemctl", "stop", BOT_SERVICE_NAME],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return True, None
        except subprocess.CalledProcessError as exc:
            return False, exc.stderr.strip() or "неизвестная ошибка"


def get_telegram_bot_status():
    try:
        result = subprocess.run(
            ["/bin/systemctl", "is-active", BOT_SERVICE_NAME],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        status = result.stdout.strip()
        return status == "active"
    except Exception:
        return False


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


def get_disabled_wg_peers():
    """Получает отключённых пиров из конфигурационных файлов WireGuard.
    Отключённые пиры имеют строки, закомментированные префиксом '#~ '."""
    configs = {
        "vpn": "/etc/wireguard/vpn.conf",
        "antizapret": "/etc/wireguard/antizapret.conf",
    }
    result = {}

    for interface, config_path in configs.items():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            continue

        disabled = []
        i = 0
        while i < len(lines):
            s = lines[i].strip()

            if s.startswith("# Client ="):
                client_name = s.split("=", 1)[1].strip()
                for j in range(i + 1, min(i + 3, len(lines))):
                    if lines[j].strip().startswith("#~ [Peer]"):
                        public_key = None
                        allowed_ips = []
                        for k in range(j + 1, min(j + 10, len(lines))):
                            ks = lines[k].strip()
                            if ks.startswith("#~ PublicKey ="):
                                public_key = ks.split("=", 1)[1].strip()
                            elif ks.startswith("#~ AllowedIPs ="):
                                allowed_ips = [
                                    ip.strip()
                                    for ip in ks.split("=", 1)[1].strip().split(",")
                                ]
                            elif not ks.startswith("#~") and ks != "":
                                break

                        if public_key:
                            masked = public_key[:4] + "..." + public_key[-4:]
                            disabled.append(
                                {
                                    "peer": public_key,
                                    "masked_peer": masked,
                                    "client": client_name,
                                    "enabled": False,
                                    "online": False,
                                    "endpoint": "N/A",
                                    "visible_ips": allowed_ips[:1],
                                    "hidden_ips": allowed_ips[1:],
                                    "latest_handshake": None,
                                    "daily_received": "0 B",
                                    "daily_sent": "0 B",
                                    "received": "0 B",
                                    "sent": "0 B",
                                    "received_bytes": 0,
                                    "sent_bytes": 0,
                                    "daily_traffic_percentage": 0,
                                    "received_percentage": 0,
                                    "sent_percentage": 0,
                                    "allowed_ips": allowed_ips,
                                }
                            )
                        break
            i += 1

        if disabled:
            result[interface] = disabled

    return result


def toggle_peer_config(config_path, public_key, enable):
    """Включает или отключает пир в конфигурационном файле WireGuard.
    Отключение добавляет префикс '#~ ' к строкам блока [Peer].
    Включение удаляет этот префикс."""
    with open(config_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    key_line_idx = None
    for i, line in enumerate(lines):
        s = line.strip()
        clean = s.replace("#~ ", "", 1) if s.startswith("#~ ") else s
        if clean.startswith("PublicKey =") and public_key in clean:
            key_line_idx = i
            break

    if key_line_idx is None:
        return False

    block_start = key_line_idx
    for i in range(key_line_idx - 1, -1, -1):
        s = lines[i].strip()
        if s.startswith("# Client ="):
            block_start = i
            break
        elif s.startswith("[Peer]") or s.startswith("#~ [Peer]"):
            block_start = i
            if i > 0 and lines[i - 1].strip().startswith("# Client ="):
                block_start = i - 1
            break
        elif s == "":
            continue
        elif s.startswith("[Interface]"):
            block_start = i + 1
            break

    block_end = key_line_idx + 1
    for i in range(key_line_idx + 1, len(lines)):
        s = lines[i].strip()
        if s.startswith("# Client =") or s.startswith("[Interface]"):
            block_end = i
            break
        if s.startswith("[Peer]") or s.startswith("#~ [Peer]"):
            block_end = i
            break
        block_end = i + 1

    new_lines = lines[:block_start]

    for i in range(block_start, block_end):
        line = lines[i]
        s = line.strip()

        if enable:
            if s.startswith("#~ "):
                new_lines.append(line.replace("#~ ", "", 1))
            else:
                new_lines.append(line)
        else:
            if s == "" or s.startswith("#"):
                new_lines.append(line)
            else:
                new_lines.append("#~ " + line.lstrip())

    new_lines.extend(lines[block_end:])

    with open(config_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return True


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


def parse_wireguard_output(output, hide_ip=True):
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
            peer_data["endpoint"] = mask_ip(line.split(": ")[1].strip(), hide=hide_ip)
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


def _ovpn_session_row_key(name, protocol):
    raw = f"{name}\x1f{protocol}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


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



def mask_ip(ip_address, hide=True):
    """Маскирует реальный IP-адрес если hide=True."""
    if not ip_address:
        return "0.0.0.0"

    port = ""
    if ":" in ip_address:
        ip, port = ip_address.rsplit(":", 1)
        port = f":{port}"
    else:
        ip = ip_address

    parts = ip.split(".")

    if len(parts) == 4:
        try:
            parts = [str(int(part)) for part in parts]
            if hide:
                return f"{parts[0]}.***.***.{parts[3]}"
            return f"{parts[0]}.{parts[1]}.{parts[2]}.{parts[3]}"
        except ValueError:
            return ip_address

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

def normalize_real_address(addr):
    if addr.startswith(("udp4:", "tcp4:", "tcp4-server:", "udp6:", "tcp6:")):
        addr = addr.split(":", 1)[1]
    return addr

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
                real_address = normalize_real_address(row[2])
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
                        real_address,
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


# Очистка БД статистики
STATS_DB_CLEAR_OVPN_PHRASE = "OpenVPN"
STATS_DB_CLEAR_WG_PHRASE = "WireGuard"


def get_ovpn_wg_database_sizes():
    """Размеры файлов БД статистики OpenVPN и WireGuard (без путей в UI)."""
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
            ("monthly_stats", "connection_logs", "last_client_stats"),
        )
        return True, None
    except Exception as e:
        return False, str(e)


def clear_wireguard_stats_database():
    """Очищает wireguard_stats.db."""
    try:
        _delete_tables_and_vacuum(
            app.config["WG_STATS_PATH"],
            ("wg_daily_stats", "wg_intermediate", "wg_total_stats"),
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
            vpn_services = get_vpn_systemd_states()

            _mem = psutil.virtual_memory()
            _disk = psutil.disk_usage("/")
            cached_system_info = {
                **HOST_STATIC_INFO,
                "cpu_load": round(cpu_percent, 1),
                "memory_used": _mem.used // (1024**2),
                "memory_total": _mem.total // (1024**2),
                "memory_percent": round(_mem.percent, 1),
                "disk_used": round(_disk.used / (1024**3), 1),
                "disk_total": round(_disk.total / (1024**3), 1),
                "network_load": get_network_load(),
                "uptime": format_uptime(get_uptime()),
                "network_interface": interface or "Не найдено",
                "rx_bytes": format_bytes(network_stats["rx"]) if network_stats else 0,
                "tx_bytes": format_bytes(network_stats["tx"]) if network_stats else 0,
                "vpn_clients": vpn_clients,
                "vpn_services": vpn_services,
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

            client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
            if client_ip and "," in client_ip:
                client_ip = client_ip.split(",")[0].strip()
            log_action("web", user["username"], user["username"], "web_login", "", client_ip or "")

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
    app_name = read_settings().get("app_name", "StatusOpenVPN")
    return {
        "hostname": socket.gethostname(),
        "server_ip": get_external_ip(),
        "version": get_git_version(),
        "base_path": request.script_root or "",
        "app_name": app_name,
        "host_os_label": HOST_STATIC_INFO["os_label"],
    }


@app.route("/")
@login_required
def home():
    server_ip = get_external_ip()
    system_info = get_system_info() or {**HOST_STATIC_INFO}
    hostname = socket.gethostname()

    return render_template(
        "index.html",
        server_ip=server_ip,
        system_info=system_info,
        hostname=hostname,
        active_page="home",
    )


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    settings_message = None
    settings_error = None
    stats_db_message = None
    stats_db_error = None

    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "settings_all":
            app_name = request.form.get("app_name", "").strip()
            hide_ovpn_ip = request.form.get("hide_ovpn_ip") == "on"
            hide_wg_ip = request.form.get("hide_wg_ip") == "on"
            retention_days = parse_stats_retention_days(
                request.form.get("stats_retention_days", "365")
            )
            write_settings(
                {
                    "app_name": app_name,
                    "hide_ovpn_ip": hide_ovpn_ip,
                    "hide_wg_ip": hide_wg_ip,
                    "stats_retention_days": retention_days,
                }
            )
            settings_message = "Настройки сохранены."

        elif form_type == "stats_db_clear_ovpn":
            phrase = (request.form.get("confirm_phrase") or "").strip()
            if phrase != STATS_DB_CLEAR_OVPN_PHRASE:
                stats_db_error = "Неверная фраза. Введите: OpenVPN"
            else:
                ok, err = clear_openvpn_stats_database()
                if ok:
                    stats_db_message = "База статистики OpenVPN очищена."
                    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
                    if client_ip and "," in client_ip:
                        client_ip = client_ip.split(",")[0].strip()
                    log_action(
                        "web",
                        current_user.username,
                        current_user.username,
                        "stats_db_clear_ovpn",
                        "",
                        client_ip or "",
                    )
                else:
                    stats_db_error = f"Ошибка очистки OpenVPN: {err}"

        elif form_type == "stats_db_clear_wg":
            phrase = (request.form.get("confirm_phrase") or "").strip()
            if phrase != STATS_DB_CLEAR_WG_PHRASE:
                stats_db_error = "Неверная фраза. Введите: WireGuard"
            else:
                ok, err = clear_wireguard_stats_database()
                if ok:
                    stats_db_message = "База статистики WireGuard очищена."
                    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
                    if client_ip and "," in client_ip:
                        client_ip = client_ip.split(",")[0].strip()
                    log_action(
                        "web",
                        current_user.username,
                        current_user.username,
                        "stats_db_clear_wg",
                        "",
                        client_ip or "",
                    )
                else:
                    stats_db_error = f"Ошибка очистки WireGuard: {err}"

    settings_data = read_settings()
    current_app_name = settings_data.get("app_name", "StatusOpenVPN")
    hide_ovpn_ip = settings_data.get("hide_ovpn_ip", True)
    hide_wg_ip = settings_data.get("hide_wg_ip", True)
    stats_retention_days = parse_stats_retention_days(
        settings_data.get("stats_retention_days", 365)
    )

    stats_db_items, stats_db_total_bytes = get_ovpn_wg_database_sizes()

    return render_template(
        "settings/settings.html",
        app_name=current_app_name,
        hide_ovpn_ip=hide_ovpn_ip,
        hide_wg_ip=hide_wg_ip,
        settings_message=settings_message,
        settings_error=settings_error,
        stats_retention_days=stats_retention_days,
        stats_db_items=stats_db_items,
        stats_db_total_fmt=format_bytes(stats_db_total_bytes),
        stats_db_message=stats_db_message,
        stats_db_error=stats_db_error,
        stats_clear_ovpn_phrase=STATS_DB_CLEAR_OVPN_PHRASE,
        stats_clear_wg_phrase=STATS_DB_CLEAR_WG_PHRASE,
        active_page="settings",
    )


@app.route("/settings/telegram", methods=["GET", "POST"])
@login_required
def settings_telegram():
    bot_message = None
    bot_error = None

    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "bot":
            old_env = read_env_values()
            old_token = old_env.get("BOT_TOKEN", "")
            old_admin_id = old_env.get("ADMIN_ID", "")
            old_settings = read_settings()
            old_bot_enabled = bool(old_settings.get("bot_enabled", False)) or get_telegram_bot_status()

            bot_token = request.form.get("bot_token", "").strip()
            admin_id = request.form.get("admin_id")
            if admin_id is None:
                admin_id = old_admin_id
            admin_id = admin_id.strip()
            bot_enabled = request.form.get("bot_enabled") == "on"
            update_env_values({"BOT_TOKEN": bot_token, "ADMIN_ID": admin_id})
            write_settings({"bot_enabled": bot_enabled})

            client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
            if client_ip and "," in client_ip:
                client_ip = client_ip.split(",")[0].strip()

            if bot_token != old_token:
                token_changed = "изменён" if bot_token else "удалён"
                log_action("web", current_user.username, current_user.username, "bot_token_change", token_changed, client_ip or "")

            if admin_id != old_admin_id:
                log_action("web", current_user.username, current_user.username, "bot_admins_change", f"{old_admin_id} → {admin_id}", client_ip or "")

            should_start = bool(bot_enabled and bot_token)

            if should_start:
                restart_ok, restart_error = restart_telegram_bot()
                if restart_ok:
                    bot_message = "Настройки бота сохранены. Бот перезапущен."
                    if not old_bot_enabled:
                        log_action("web", current_user.username, current_user.username, "bot_toggle", "включён", client_ip or "")
                else:
                    bot_error = (
                        "Настройки бота сохранены, но перезапуск не удался: "
                        f"{restart_error}"
                    )
            else:
                restart_ok, restart_error = stop_telegram_bot()
                if restart_ok:
                    if not bot_token:
                        bot_message = (
                            "Настройки бота сохранены. API токен бота пустой, бот остановлен."
                        )
                    else:
                        bot_message = "Настройки бота сохранены. Бот остановлен."
                    if old_bot_enabled:
                        log_action("web", current_user.username, current_user.username, "bot_toggle", "отключён", client_ip or "")
                else:
                    bot_error = (
                        "Настройки бота сохранены, но остановка не удалась: "
                        f"{restart_error}"
                    )

    env_values = read_env_values()
    bot_token_value = env_values.get("BOT_TOKEN", "")
    admin_id_value = env_values.get("ADMIN_ID", "")
    settings_data = read_settings()
    admin_info = settings_data.get("telegram_admins", {})
    admin_display_list = build_admin_display_list(admin_id_value, admin_info)
    available_admins = build_available_admin_candidates(
        admin_info, parse_admin_ids(admin_id_value)
    )
    client_mapping_list = build_client_mapping_list(env_values, admin_info)
    bot_service_active = get_telegram_bot_status()
    bot_enabled = bool(settings_data.get("bot_enabled", False)) or bot_service_active

    return render_template(
        "settings/telegram.html",
        bot_token=bot_token_value,
        admin_id=admin_id_value,
        admin_display_list=admin_display_list,
        available_admins=available_admins,
        client_mapping_list=client_mapping_list,
        bot_service_active=bot_service_active,
        bot_enabled=bot_enabled,
        bot_message=bot_message,
        bot_error=bot_error,
        active_page="settings_telegram",
    )


@app.route("/settings/audit")
@login_required
def settings_audit():
    page = request.args.get("page", 1, type=int)
    action_filter = request.args.get("action", None)
    per_page = 20

    if action_filter == "all":
        action_filter = None

    total = get_logs_count(action_filter)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page

    logs = get_logs(limit=per_page, offset=offset, action_filter=action_filter)

    action_labels = {
        "client_create": "Создание клиента",
        "client_delete": "Удаление клиента",
        "files_recreate": "Пересоздание файлов",
        "server_reboot": "Перезагрузка сервера",
        "web_login": "Вход в панель",
        "peer_toggle": "Переключение WG пира",
        "bot_token_change": "Изменение токена бота",
        "bot_admins_change": "Изменение админов бота",
        "bot_toggle": "Вкл/выкл бота",
        "request_approve": "Привязка клиента",
        "request_reject": "Отклонение запроса",
        "stats_db_clear_ovpn": "Очистка БД OpenVPN",
        "stats_db_clear_wg": "Очистка БД WireGuard",
    }

    return render_template(
        "settings/audit.html",
        logs=logs,
        page=page,
        total_pages=total_pages,
        action_filter=action_filter or "all",
        action_labels=action_labels,
        active_page="settings_audit",
    )


@app.route("/settings/install")
@login_required
def settings_install():
    antizapret_pairs, antizapret_error = read_setup_key_value_file(ANTIZAPRET_SETUP_PATH)
    antizapret_rows = [
        (key, value, ANTIZAPRET_SETUP_DESCRIPTIONS.get(key, ""))
        for key, value in antizapret_pairs
    ]
    web_pairs, web_error = read_setup_key_value_file(STATUSOPENVPN_SETUP_PATH)
    web_rows = [
        (key, value, WEB_SETUP_DESCRIPTIONS.get(key, ""))
        for key, value in web_pairs
    ]
    return render_template(
        "settings/install.html",
        antizapret_rows=antizapret_rows,
        antizapret_error=antizapret_error,
        antizapret_path=ANTIZAPRET_SETUP_PATH,
        web_rows=web_rows,
        web_error=web_error,
        web_path=STATUSOPENVPN_SETUP_PATH,
        active_page="settings_install",
    )


@app.route("/settings/install/download")
@login_required
def settings_install_download():
    """Скачивание файла параметров установки Antizapret с сервера."""
    path = ANTIZAPRET_SETUP_PATH
    if not os.path.isfile(path):
        abort(404)
    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path),
        mimetype="text/plain",
    )


@app.route("/settings/install/download/statusopenvpn")
@login_required
def settings_install_download_statusopenvpn():
    """Скачивание файла параметров установки StatusOpenVPN (веб-приложения) с сервера."""
    path = STATUSOPENVPN_SETUP_PATH
    if not os.path.isfile(path):
        abort(404)
    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path),
        mimetype="text/plain",
    )


@app.route("/api/admins/add", methods=["POST"])
@login_required
def api_admins_add():
    payload = request.get_json(silent=True) or {}
    telegram_id = str(payload.get("telegram_id", "")).strip()
    if not telegram_id:
        return jsonify({"success": False, "message": "ID не указан."}), 400

    admin_info = read_admin_info()

    env_values = read_env_values()
    admin_id_value = env_values.get("ADMIN_ID", "")
    admin_ids = parse_admin_ids(admin_id_value)
    if telegram_id in admin_ids:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Администратор уже в списке.",
                    "admins": build_admin_display_list(admin_id_value, admin_info),
                    "available_admins": build_available_admin_candidates(
                        admin_info, admin_ids
                    ),
                    "admin_id_value": admin_id_value,
                    "bot_service_active": get_telegram_bot_status(),
                }
            ),
            400,
        )

    admin_ids.append(telegram_id)
    updated_admin_id_value = format_admin_ids(admin_ids)
    update_env_values({"ADMIN_ID": updated_admin_id_value})

    admin_display_list = build_admin_display_list(updated_admin_id_value, admin_info)
    available_admins = build_available_admin_candidates(admin_info, admin_ids)
    response = {
        "success": True,
        "message": "Администратор добавлен. Нажмите «Сохранить», чтобы применить изменения.",
        "admins": admin_display_list,
        "available_admins": available_admins,
        "admin_id_value": updated_admin_id_value,
        "bot_service_active": get_telegram_bot_status(),
    }
    return jsonify(response), 200


@app.route("/api/admins/remove", methods=["POST"])
@login_required
def api_admins_remove():
    payload = request.get_json(silent=True) or {}
    telegram_id = str(payload.get("telegram_id", "")).strip()
    if not telegram_id:
        return jsonify({"success": False, "message": "ID не указан."}), 400

    admin_info = read_admin_info()
    env_values = read_env_values()
    admin_id_value = env_values.get("ADMIN_ID", "")
    admin_ids = parse_admin_ids(admin_id_value)
    if telegram_id not in admin_ids:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Администратор не найден в списке.",
                    "admins": build_admin_display_list(admin_id_value, admin_info),
                    "available_admins": build_available_admin_candidates(
                        admin_info, admin_ids
                    ),
                    "admin_id_value": admin_id_value,
                    "bot_service_active": get_telegram_bot_status(),
                }
            ),
            400,
        )

    if len(admin_ids) <= 1:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Нельзя удалить последнего администратора.",
                    "admins": build_admin_display_list(admin_id_value, admin_info),
                    "available_admins": build_available_admin_candidates(
                        admin_info, admin_ids
                    ),
                    "admin_id_value": admin_id_value,
                    "bot_service_active": get_telegram_bot_status(),
                }
            ),
            400,
        )

    admin_ids = [admin_id for admin_id in admin_ids if admin_id != telegram_id]
    updated_admin_id_value = format_admin_ids(admin_ids)
    update_env_values({"ADMIN_ID": updated_admin_id_value})

    admin_display_list = build_admin_display_list(updated_admin_id_value, admin_info)
    available_admins = build_available_admin_candidates(admin_info, admin_ids)
    response = {
        "success": True,
        "message": "Администратор удалён. Нажмите «Сохранить», чтобы применить изменения.",
        "admins": admin_display_list,
        "available_admins": available_admins,
        "admin_id_value": updated_admin_id_value,
        "bot_service_active": get_telegram_bot_status(),
    }
    return jsonify(response), 200


@app.route("/api/system_info")
@login_required
def api_system_info():
    system_info = get_system_info()
    return jsonify(system_info)


@app.route("/api/vpn-service/restart", methods=["POST"])
@login_required
def api_restart_vpn_service():
    data = request.get_json(silent=True) or {}
    unit = data.get("unit")
    if not unit or not isinstance(unit, str) or unit not in VPN_SYSTEMD_UNIT_SET:
        return jsonify({"ok": False, "error": "Недопустимый unit"}), 400
    ok, detail = restart_vpn_systemd_unit(unit)
    if ok:
        return jsonify({"ok": True, "detail": detail})
    return jsonify({"ok": False, "error": detail}), 500


@app.route("/api/ovpn/next_update")
@login_required
def api_ovpn_next_update():
    """
    Возвращает оценку времени следующего обновления логов OpenVPN.
    Основано на mtime файлов status.log + фиксированный интервал 30 секунд.
    """
    file_paths = [
        ("/etc/openvpn/server/logs/antizapret-udp-status.log", "UDP"),
        ("/etc/openvpn/server/logs/antizapret-tcp-status.log", "TCP"),
        ("/etc/openvpn/server/logs/vpn-udp-status.log", "VPN-UDP"),
        ("/etc/openvpn/server/logs/vpn-tcp-status.log", "VPN-TCP"),
    ]

    mtimes = []
    for path, _ in file_paths:
        try:
            if os.path.exists(path):
                mtimes.append(os.path.getmtime(path))
        except OSError:
            continue

    now_ts = time.time()

    if not mtimes:
        next_update_ts = now_ts + 30
    else:
        last_mtime = max(mtimes)
        next_update_ts = last_mtime + 30
        if next_update_ts <= now_ts:
            next_update_ts = now_ts + 30

    return jsonify(
        {
            "server_time": int(now_ts),
            "next_update_ts": int(next_update_ts),
            "interval_seconds": 30,
        }
    )


@app.route("/wg")
@login_required
def wg():
    """Маршрут клиентов WireGuard"""
    hide_wg_ip = read_settings().get("hide_wg_ip", True)
    stats = parse_wireguard_output(get_wireguard_stats(), hide_ip=hide_wg_ip)
    disabled_peers = get_disabled_wg_peers()
    for interface_data in stats:
        for peer in interface_data.get("peers", []):
            peer["enabled"] = True
        iface = interface_data.get("interface")
        if iface in disabled_peers:
            interface_data.setdefault("peers", []).extend(disabled_peers[iface])

    return render_template("wg/wg.html", stats=stats, active_section="wg", active_page="wg_clients")


@app.route("/wg/client-status")
@login_required
def wg_client_status():
    """Старая страница статуса объединена с разделом «Клиенты»."""
    return redirect(url_for("wg"))


@app.route("/api/wg/stats")
@login_required
def api_wg_stats():
    try:
        hide_wg_ip = read_settings().get("hide_wg_ip", True)
        stats = parse_wireguard_output(get_wireguard_stats(), hide_ip=hide_wg_ip)
        disabled_peers = get_disabled_wg_peers()
        for interface_data in stats:
            for peer in interface_data.get("peers", []):
                peer["enabled"] = True
            iface = interface_data.get("interface")
            if iface in disabled_peers:
                interface_data.setdefault("peers", []).extend(disabled_peers[iface])
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/wg/peer/toggle", methods=["POST"])
@login_required
def toggle_wg_peer():
    data = request.get_json()
    peer = data.get("peer")
    interface = data.get("interface")
    enable = data.get("enable")

    if not peer or not interface or enable is None:
        return jsonify({"error": "Отсутствуют обязательные параметры"}), 400

    config_path = f"/etc/wireguard/{interface}.conf"

    if not os.path.exists(config_path):
        return jsonify({"error": "Конфигурация не найдена"}), 404

    try:
        success = toggle_peer_config(config_path, peer, enable)
        if not success:
            return jsonify({"error": "Пир не найден в конфигурации"}), 404

        wg_quick = shutil.which("wg-quick") or "/usr/bin/wg-quick"
        wg_bin = shutil.which("wg") or "/usr/bin/wg"
        if not os.path.isfile(wg_quick):
            return jsonify({"error": "wg-quick не найден. Установите wireguard-tools."}), 500
        if not os.path.isfile(wg_bin):
            return jsonify({"error": "wg не найден. Установите wireguard-tools."}), 500

        subprocess.run(
            [
                "/bin/bash",
                "-c",
                f"{wg_bin} syncconf {interface} <({wg_quick} strip {interface})",
            ],
            check=True,
            env={**os.environ, "PATH": "/usr/bin:/bin"},
        )

        client_name = data.get("client_name", peer[:8] + "...")
        action_str = "включён" if enable else "отключён"
        log_action("web", current_user.username, current_user.username, "peer_toggle", f"{client_name} ({action_str})")

        return jsonify({"success": True, "enabled": enable})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/wg/stats")
@login_required
def wg_stats():
    try:
        sort_by = request.args.get("sort", "client")
        order = request.args.get("order", "asc").lower()
        period = request.args.get("period", "month")
        now = datetime.now()
        selected_date_from = (request.args.get("date_from") or "").strip()
        selected_date_to = (request.args.get("date_to") or "").strip()

        allowed_sorts = {
            "client": "client",
            "total_sent": "SUM(sent)",
            "total_received": "SUM(received)",
        }

        sort_column = allowed_sorts.get(sort_by, "client")
        order_sql = "DESC" if order == "desc" else "ASC"
        if period == "day":
            date_from = now.strftime("%Y-%m-%d")
            date_to = None
            interval_label = f"за {now.strftime('%d.%m.%Y')}"
        elif period == "week":
            week_start = now - timedelta(days=7)
            date_from = week_start.strftime("%Y-%m-%d")
            date_to = None
            interval_label = f"с {week_start.strftime('%d.%m.%Y')} по {now.strftime('%d.%m.%Y')}"
        elif period == "year":
            year_start = now - timedelta(days=365)
            date_from = year_start.strftime("%Y-%m-%d")
            date_to = None
            interval_label = f"с {year_start.strftime('%d.%m.%Y')} по {now.strftime('%d.%m.%Y')}"
        elif period == "custom":
            date_from_dt = parse_date_yyyy_mm_dd(selected_date_from)
            date_to_dt = parse_date_yyyy_mm_dd(selected_date_to)
            if date_from_dt and date_to_dt:
                if date_from_dt > date_to_dt:
                    date_from_dt, date_to_dt = date_to_dt, date_from_dt
                selected_date_from = date_from_dt.strftime("%Y-%m-%d")
                selected_date_to = date_to_dt.strftime("%Y-%m-%d")
                date_from = selected_date_from
                date_to = (date_to_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                interval_label = f"с {date_from_dt.strftime('%d.%m.%Y')} по {date_to_dt.strftime('%d.%m.%Y')}"
            else:
                period = "month"
                date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
                date_to = None
                interval_label = f"с {(now - timedelta(days=30)).strftime('%d.%m.%Y')} по {now.strftime('%d.%m.%Y')}"
        else:
            period = "month"
            date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            date_to = None
            interval_label = f"с {(now - timedelta(days=30)).strftime('%d.%m.%Y')} по {now.strftime('%d.%m.%Y')}"

        stats_list = []
        total_received, total_sent = 0, 0

        with sqlite3.connect(app.config["WG_STATS_PATH"]) as conn:
            if date_to:
                query = f"""
                    SELECT client,
                           SUM(received) as total_received,
                           SUM(sent) as total_sent
                    FROM wg_daily_stats
                    WHERE date >= ? AND date < ?
                    GROUP BY client
                    ORDER BY {sort_column} {order_sql}
                """
                rows = conn.execute(query, (date_from, date_to)).fetchall()
            else:
                query = f"""
                    SELECT client,
                           SUM(received) as total_received,
                           SUM(sent) as total_sent
                    FROM wg_daily_stats
                    WHERE date >= ?
                    GROUP BY client
                    ORDER BY {sort_column} {order_sql}
                """
                rows = conn.execute(query, (date_from,)).fetchall()

            for row in rows:
                client, received, sent = row
                received = received or 0
                sent = sent or 0
                total_received += received
                total_sent += sent
                stats_list.append(
                    {
                        "client": client,
                        "total_received": format_bytes(received),
                        "total_sent": format_bytes(sent),
                    }
                )

        return render_template(
            "wg/wg_stats.html",
            total_received=format_bytes(total_received),
            total_sent=format_bytes(total_sent),
            active_section="wg",
            active_page="wg_stats",
            stats=stats_list,
            period=period,
            sort_by=sort_by,
            order=order_sql.lower(),
            selected_date_from=selected_date_from,
            selected_date_to=selected_date_to,
            interval_label=interval_label,
        )

    except Exception as e:
        error_message = f"Произошла непредвиденная ошибка: {e}"
        return render_template(
            "wg/wg_stats.html",
            error_message=error_message,
            active_section="wg",
            active_page="wg_stats",
        ), 500


def _collect_openvpn_clients_unsorted():
    """Собирает список клиентов OpenVPN без сортировки.
    Возвращает (all_clients_list, total_received, total_sent, errors)."""
    file_paths = [
        ("/etc/openvpn/server/logs/antizapret-udp-status.log", "UDP"),
        ("/etc/openvpn/server/logs/antizapret-tcp-status.log", "TCP"),
        ("/etc/openvpn/server/logs/vpn-udp-status.log", "VPN-UDP"),
        ("/etc/openvpn/server/logs/vpn-tcp-status.log", "VPN-TCP"),
    ]

    online_clients_raw = []
    total_received, total_sent = 0, 0
    errors = []
    online_client_names = set()

    for file_path, protocol in file_paths:
        file_data, received, sent, error = read_csv(file_path, protocol)
        if error:
            errors.append(f"Ошибка в файле {file_path}: {error}")
        else:
            online_clients_raw.extend(file_data)
            total_received += received
            total_sent += sent
            for client_row in file_data:
                if client_row[0] != "UNDEF":
                    online_client_names.add(client_row[0])

    all_clients = get_all_openvpn_clients()
    banned_clients = _read_banned_clients()
    server_ip = get_external_ip()

    all_clients_list = []

    for client_row in online_clients_raw:
        client_name = client_row[0]
        if client_name == "UNDEF":
            continue
        is_blocked = client_name in banned_clients
        all_clients_list.append(
            {
                "name": client_name,
                "display_name": clean_client_display_name(client_name, server_ip),
                "online": True,
                "blocked": is_blocked,
                "real_ip": client_row[1],
                "local_ip": client_row[2],
                "received": client_row[3],
                "sent": client_row[4],
                "download_speed": client_row[5],
                "upload_speed": client_row[6],
                "connected_since": client_row[7],
                "duration": client_row[8],
                "protocol": client_row[9],
            }
        )

    for client_name in sorted(all_clients):
        if client_name not in online_client_names:
            is_blocked = client_name in banned_clients
            all_clients_list.append(
                {
                    "name": client_name,
                    "display_name": clean_client_display_name(
                        client_name, server_ip
                    ),
                    "online": False,
                    "blocked": is_blocked,
                    "real_ip": "-",
                    "local_ip": "-",
                    "received": "-",
                    "sent": "-",
                    "download_speed": "-",
                    "upload_speed": "-",
                    "connected_since": "-",
                    "duration": "-",
                    "protocol": "-",
                }
            )

    return all_clients_list, total_received, total_sent, errors


def _build_openvpn_client_status_sorted(sort_by, order):
    """Список клиентов для страницы статуса: сертификат, сортировка client/status/cert.
    Возвращает (all_clients_list, errors, total_online)."""
    all_clients_list, _, _, errors = _collect_openvpn_clients_unsorted()
    for row in all_clients_list:
        exp_dt, exp_label = _get_openvpn_client_cert_expiry(row["name"])
        row["cert_expiry_dt"] = exp_dt
        row["cert_expiry_label"] = exp_label
        days_left, days_label = _cert_days_left_fields(exp_dt)
        row["cert_days_left"] = days_left
        row["cert_days_left_label"] = days_label

    if sort_by == "cert":
        valid = [x for x in all_clients_list if x["cert_expiry_dt"] is not None]
        missing = [x for x in all_clients_list if x["cert_expiry_dt"] is None]
        valid.sort(key=lambda x: x["cert_expiry_dt"], reverse=(order == "desc"))
        all_clients_list = valid + missing
    else:
        reverse_order = order == "desc"

        def sort_key(x):
            if sort_by == "client":
                return (x["name"].lower(),)
            if sort_by == "status":
                return (0 if x["online"] else 1, 0 if not x["blocked"] else 1)
            online_priority = 0 if x["online"] else 1
            return (online_priority, x["name"].lower())

        all_clients_list.sort(key=sort_key, reverse=reverse_order)

    total_online = len([c for c in all_clients_list if c["online"]])
    return all_clients_list, errors, total_online


def _build_openvpn_clients_sorted(sort_by, order):
    """Собирает список клиентов OpenVPN и сортирует. Возвращает
    (all_clients_list, total_received, total_sent, errors, total_online)."""
    all_clients_list, total_received, total_sent, errors = (
        _collect_openvpn_clients_unsorted()
    )

    reverse_order = order == "desc"

    def sort_key(x):
        online_priority = 0 if x["online"] else 1
        if sort_by == "client":
            return (online_priority, x["name"].lower())
        elif sort_by == "realIp":
            return (online_priority, x["real_ip"])
        elif sort_by == "localIp":
            return (online_priority, x["local_ip"])
        elif sort_by == "sent":
            return (
                online_priority,
                parse_bytes(x["sent"]) if x["sent"] != "-" else -1,
            )
        elif sort_by == "received":
            return (
                online_priority,
                parse_bytes(x["received"]) if x["received"] != "-" else -1,
            )
        elif sort_by == "connection-time":
            return (
                online_priority,
                x["connected_since"] if x["connected_since"] != "-" else "",
            )
        elif sort_by == "duration":
            return (
                online_priority,
                x["connected_since"] if x["connected_since"] != "-" else "",
            )
        elif sort_by == "protocol":
            return (online_priority, x["protocol"])
        elif sort_by == "status":
            return (0 if x["online"] else 1, 0 if not x["blocked"] else 1)
        return (online_priority, x["name"].lower())

    all_clients_list.sort(key=sort_key, reverse=reverse_order)

    total_online = len([c for c in all_clients_list if c["online"]])
    for c in all_clients_list:
        c["row_key"] = _ovpn_session_row_key(c["name"], c["protocol"])
    return all_clients_list, total_received, total_sent, errors, total_online


@app.route("/api/ovpn/clients")
@login_required
def api_ovpn_clients():
    """JSON-снимок списка OpenVPN для частичного обновления страницы /ovpn."""
    sort_by = request.args.get("sort", "client")
    order = request.args.get("order", "asc")
    try:
        all_clients_list, total_received, total_sent, errors, total_online = (
            _build_openvpn_clients_sorted(sort_by, order)
        )
        online = [c for c in all_clients_list if c["online"]]
        return jsonify(
            {
                "ok": True,
                "online": online,
                "total_received": format_bytes(total_received),
                "total_sent": format_bytes(total_sent),
                "total_clients_str": pluralize_clients(total_online),
                "total_online": total_online,
                "errors": errors,
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/ovpn")
@login_required
def ovpn():
    try:
        sort_by = request.args.get("sort", "client")
        order = request.args.get("order", "asc")
        all_clients_list, total_received, total_sent, errors, total_online = (
            _build_openvpn_clients_sorted(sort_by, order)
        )
        return render_template(
            "ovpn/ovpn.html",
            clients=all_clients_list,
            total_clients_str=pluralize_clients(total_online),
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
        return render_template(
            "ovpn/ovpn.html",
            error_message=error_message,
            active_section="ovpn",
            active_page="clients",
        ), 500

    except Exception as e:
        error_message = f"Произошла непредвиденная ошибка: {str(e)}"
        return render_template(
            "ovpn/ovpn.html",
            error_message=error_message,
            active_section="ovpn",
            active_page="clients",
        ), 500


@app.route("/ovpn/client-status")
@login_required
def ovpn_client_status():
    try:
        sort_by = request.args.get("sort", "client")
        order = request.args.get("order", "asc")
        all_clients_list, errors, total_online = _build_openvpn_client_status_sorted(
            sort_by, order
        )
        return render_template(
            "ovpn/ovpn_client_status.html",
            clients=all_clients_list,
            total_clients_str=pluralize_clients(total_online),
            active_section="ovpn",
            active_page="client_status",
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
        return render_template(
            "ovpn/ovpn_client_status.html",
            error_message=error_message,
            active_section="ovpn",
            active_page="client_status",
        ), 500

    except Exception as e:
        error_message = f"Произошла непредвиденная ошибка: {str(e)}"
        return render_template(
            "ovpn/ovpn_client_status.html",
            error_message=error_message,
            active_section="ovpn",
            active_page="client_status",
        ), 500


@app.route("/ovpn/history")
@login_required
def ovpn_history():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = 20

        conn_logs = sqlite3.connect(app.config["LOGS_DATABASE_PATH"])
        
        total_count = conn_logs.execute(
            "SELECT COUNT(*) FROM connection_logs WHERE client_name != 'UNDEF'"
        ).fetchone()[0]
        
        total_pages = max(1, (total_count + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        offset = (page - 1) * per_page

        logs_reader = conn_logs.execute(
            """SELECT * FROM connection_logs 
               WHERE client_name != 'UNDEF'
               ORDER BY connected_since DESC 
               LIMIT ? OFFSET ?""",
            (per_page, offset),
        ).fetchall()
        conn_logs.close()

        hide_ovpn_ip = read_settings().get("hide_ovpn_ip", True)

        def format_ip(ip):
            real_ip = normalize_real_address(ip)
            return mask_ip(real_ip, hide=hide_ovpn_ip)

        logs = [
            {
                "client_name": row[1],
                "real_ip": format_ip(row[3]),
                "local_ip": row[2],
                "connection_since": row[4],
                "protocol": row[7],
            }
            for row in logs_reader
        ]

        return render_template(
            "ovpn/ovpn_history.html",
            active_section="ovpn",
            active_page="history",
            logs=logs,
            page=page,
            total_pages=total_pages,
        )

    except Exception as e:
        error_message = f"Произошла непредвиденная ошибка: {str(e)}"
        return render_template(
            "ovpn/ovpn_history.html",
            error_message=error_message,
            active_section="ovpn",
            active_page="history",
        ), 500


@app.route("/ovpn/stats")
@login_required
def ovpn_stats():
    try:
        sort_by = request.args.get("sort", "client_name")
        order = request.args.get("order", "asc").lower()
        period = request.args.get("period", "month")
        now = datetime.now()
        selected_date_from = (request.args.get("date_from") or "").strip()
        selected_date_to = (request.args.get("date_to") or "").strip()

        allowed_sorts = {
            "client_name": "client_name",
            "total_bytes_sent": "SUM(total_bytes_received)",
            "total_bytes_received": "SUM(total_bytes_sent)",
            "last_connected": "MAX(last_connected)",
        }

        sort_column = allowed_sorts.get(sort_by, "client_name")
        order_sql = "DESC" if order == "desc" else "ASC"
        if period == "day":
            date_from = now.strftime("%Y-%m-%d")
            date_to = None
            interval_label = f"за {now.strftime('%d.%m.%Y')}"
        elif period == "week":
            week_start = now - timedelta(days=7)
            date_from = week_start.strftime("%Y-%m-%d")
            date_to = None
            interval_label = f"с {week_start.strftime('%d.%m.%Y')} по {now.strftime('%d.%m.%Y')}"
        elif period == "year":
            year_start = now - timedelta(days=365)
            date_from = year_start.strftime("%Y-%m-%d")
            date_to = None
            interval_label = f"с {year_start.strftime('%d.%m.%Y')} по {now.strftime('%d.%m.%Y')}"
        elif period == "custom":
            date_from_dt = parse_date_yyyy_mm_dd(selected_date_from)
            date_to_dt = parse_date_yyyy_mm_dd(selected_date_to)
            if date_from_dt and date_to_dt:
                if date_from_dt > date_to_dt:
                    date_from_dt, date_to_dt = date_to_dt, date_from_dt
                selected_date_from = date_from_dt.strftime("%Y-%m-%d")
                selected_date_to = date_to_dt.strftime("%Y-%m-%d")
                date_from = selected_date_from
                date_to = (date_to_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                interval_label = f"с {date_from_dt.strftime('%d.%m.%Y')} по {date_to_dt.strftime('%d.%m.%Y')}"
            else:
                period = "month"
                date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
                date_to = None
                interval_label = f"с {(now - timedelta(days=30)).strftime('%d.%m.%Y')} по {now.strftime('%d.%m.%Y')}"
        else:
            period = "month"
            date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            date_to = None
            interval_label = f"с {(now - timedelta(days=30)).strftime('%d.%m.%Y')} по {now.strftime('%d.%m.%Y')}"

        stats_list = []
        total_received, total_sent = 0, 0

        with sqlite3.connect(app.config["LOGS_DATABASE_PATH"]) as conn:
            if date_to:
                query = f"""
                    SELECT client_name,
                           SUM(total_bytes_sent),
                           SUM(total_bytes_received),
                           MAX(last_connected)
                    FROM monthly_stats
                    WHERE month >= ? AND month < ?
                    GROUP BY client_name
                    ORDER BY {sort_column} {order_sql}
                """
                rows = conn.execute(query, (date_from, date_to)).fetchall()
            else:
                query = f"""
                    SELECT client_name,
                           SUM(total_bytes_sent),
                           SUM(total_bytes_received),
                           MAX(last_connected)
                    FROM monthly_stats
                    WHERE month >= ?
                    GROUP BY client_name
                    ORDER BY {sort_column} {order_sql}
                """
                rows = conn.execute(query, (date_from,)).fetchall()

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

        return render_template(
            "ovpn/ovpn_stats.html",
            total_received=format_bytes(total_received),
            total_sent=format_bytes(total_sent),
            active_section="ovpn",
            active_page="stats",
            stats=stats_list,
            period=period,
            sort_by=sort_by,
            order=order_sql.lower(),
            selected_date_from=selected_date_from,
            selected_date_to=selected_date_to,
            interval_label=interval_label,
        )

    except Exception as e:
        error_message = f"Произошла непредвиденная ошибка: {e}"
        return render_template(
            "ovpn/ovpn_stats.html",
            error_message=error_message,
            active_section="ovpn",
            active_page="stats",
        ), 500


@app.route("/api/openvpn/client-block", methods=["POST"])
@login_required
def api_openvpn_client_block():
    client_name = request.form.get("client_name", "").strip()
    blocked_raw = request.form.get("blocked", "").strip().lower()

    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    should_block = blocked_raw in {"1", "true", "yes", "on"}

    try:
        _ensure_client_connect_ban_check_block()
        banned_clients = _read_banned_clients()

        if should_block:
            banned_clients.add(client_name)
        else:
            banned_clients.discard(client_name)

        _write_banned_clients(banned_clients)
        return jsonify(
            {
                "success": True,
                "client_name": client_name,
                "blocked": should_block,
                "message": (
                    "Клиент заблокирован." if should_block else "Блокировка снята."
                ),
            }
        )
    except PermissionError:
        return (
            jsonify(
                {"success": False, "message": "Нет прав на запись banned_clients."}
            ),
            500,
        )
    except OSError as e:
        return (
            jsonify(
                {"success": False, "message": f"Ошибка работы с banned_clients: {e}"}
            ),
            500,
        )


@app.route("/api/openvpn/client-kick", methods=["POST"])
@login_required
def api_openvpn_client_kick():
    client_name = request.form.get("client_name", "").strip()
    protocol = request.form.get("protocol", "").strip() or None

    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    try:
        _ensure_client_connect_ban_check_block()
        banned_clients = _read_banned_clients()
        banned_clients.add(client_name)
        _write_banned_clients(banned_clients)

        kicked, errors = kick_openvpn_client(client_name, protocol)

        if kicked:
            return jsonify(
                {
                    "success": True,
                    "client_name": client_name,
                    "kicked": True,
                    "blocked": True,
                    "message": "Клиент отключён и заблокирован.",
                }
            )
        return jsonify(
            {
                "success": True,
                "client_name": client_name,
                "kicked": False,
                "blocked": True,
                "message": "Клиент заблокирован. Отключение не удалось (возможно, уже оффлайн).",
                "errors": errors,
            }
        )

    except PermissionError:
        return (
            jsonify(
                {"success": False, "message": "Нет прав на запись banned_clients."}
            ),
            500,
        )
    except OSError as e:
        return jsonify({"success": False, "message": f"Ошибка: {e}"}), 500


@app.route("/api/openvpn/client-config", methods=["GET"])
@login_required
def api_openvpn_client_config():
    """Список профилей .ovpn или содержимое по index."""
    client_name = request.args.get("client_name", "").strip()
    idx_raw = request.args.get("index", "").strip()

    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    paths = _list_openvpn_ovpn_paths_for_client(client_name)
    if idx_raw == "":
        items = [{"index": i, "label": _ovpn_profile_label(p)} for i, p in enumerate(paths)]
        return jsonify({"success": True, "items": items})

    try:
        idx = int(idx_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Некорректный index."}), 400

    if idx < 0 or idx >= len(paths):
        return jsonify({"success": False, "message": "Профиль не найден."}), 404

    path = paths[idx]
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        return jsonify({"success": False, "message": str(e)}), 500

    return jsonify(
        {
            "success": True,
            "config_text": text,
            "label": _ovpn_profile_label(path),
            "filename": os.path.basename(path),
        }
    )


@app.route("/api/openvpn/client-config/download", methods=["GET"])
@login_required
def api_openvpn_client_config_download():
    """Скачивание .ovpn по имени клиента и индексу профиля."""
    client_name = request.args.get("client_name", "").strip()
    idx_raw = request.args.get("index", "0").strip()

    if not CLIENT_NAME_PATTERN.fullmatch(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    try:
        idx = int(idx_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Некорректный index."}), 400

    paths = _list_openvpn_ovpn_paths_for_client(client_name)
    if idx < 0 or idx >= len(paths):
        return jsonify({"success": False, "message": "Профиль не найден."}), 404

    path = paths[idx]
    if not os.path.isfile(path):
        return jsonify({"success": False, "message": "Файл не найден."}), 404

    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path),
        mimetype="application/x-openvpn-profile",
    )


@app.route("/api/wireguard/client-config", methods=["GET"])
@login_required
def api_wireguard_client_config():
    """Список .conf профилей или содержимое по index (скачивание)."""
    client_name = request.args.get("client_name", "").strip()
    idx_raw = request.args.get("index", "").strip()

    if not _wg_client_name_param_ok(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    paths = _list_wg_conf_paths_for_client(client_name)
    if idx_raw == "":
        items = [
            {
                "index": i,
                "label": _wg_conf_profile_label(p),
                "filename": os.path.basename(p),
            }
            for i, p in enumerate(paths)
        ]
        return jsonify({"success": True, "items": items})

    try:
        idx = int(idx_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Некорректный index."}), 400

    if idx < 0 or idx >= len(paths):
        return jsonify({"success": False, "message": "Профиль не найден."}), 404

    path = paths[idx]
    if not _wg_conf_path_is_allowed(path):
        return jsonify({"success": False, "message": "Недопустимый путь."}), 403

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        return jsonify({"success": False, "message": str(e)}), 500

    return jsonify(
        {
            "success": True,
            "config_text": text,
            "label": _wg_conf_profile_label(path),
            "filename": os.path.basename(path),
        }
    )


@app.route("/api/wireguard/client-config/download", methods=["GET"])
@login_required
def api_wireguard_client_config_download():
    """Скачивание .conf по имени клиента и индексу профиля."""
    client_name = request.args.get("client_name", "").strip()
    idx_raw = request.args.get("index", "0").strip()

    if not _wg_client_name_param_ok(client_name):
        return jsonify({"success": False, "message": "Некорректное имя клиента."}), 400

    try:
        idx = int(idx_raw)
    except ValueError:
        return jsonify({"success": False, "message": "Некорректный index."}), 400

    paths = _list_wg_conf_paths_for_client(client_name)
    if idx < 0 or idx >= len(paths):
        return jsonify({"success": False, "message": "Профиль не найден."}), 404

    path = paths[idx]
    if not _wg_conf_path_is_allowed(path):
        return jsonify({"success": False, "message": "Недопустимый путь."}), 403

    if not os.path.isfile(path):
        return jsonify({"success": False, "message": "Файл не найден."}), 404

    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path),
        mimetype="text/plain",
    )


@app.route("/api/ovpn/client_chart")
@login_required
def api_ovpn_client_chart():
    client_name = request.args.get("client")
    period = request.args.get("period", "month")
    now = datetime.now()
    selected_date_from = (request.args.get("date_from") or "").strip()
    selected_date_to = (request.args.get("date_to") or "").strip()
    if not client_name:
        return jsonify({"error": "client parameter required"}), 400

    if period == "day":
        date_from = now.strftime("%Y-%m-%d")
        date_to = None
    elif period == "week":
        date_from = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        date_to = None
    elif period == "year":
        date_from = (now - timedelta(days=365)).strftime("%Y-%m-%d")
        date_to = None
    elif period == "custom":
        date_from_dt = parse_date_yyyy_mm_dd(selected_date_from)
        date_to_dt = parse_date_yyyy_mm_dd(selected_date_to)
        if date_from_dt and date_to_dt:
            if date_from_dt > date_to_dt:
                date_from_dt, date_to_dt = date_to_dt, date_from_dt
            date_from = date_from_dt.strftime("%Y-%m-%d")
            date_to = (date_to_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            date_to = None
    else:
        date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        date_to = None

    try:
        with sqlite3.connect(app.config["LOGS_DATABASE_PATH"]) as conn:
            if date_to:
                rows = conn.execute(
                    """
                    SELECT month,
                           SUM(total_bytes_received) as rx,
                           SUM(total_bytes_sent) as tx
                    FROM monthly_stats
                    WHERE client_name = ? AND month >= ? AND month < ?
                    GROUP BY month
                    ORDER BY month ASC
                    """,
                    (client_name, date_from, date_to),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT month,
                           SUM(total_bytes_received) as rx,
                           SUM(total_bytes_sent) as tx
                    FROM monthly_stats
                    WHERE client_name = ? AND month >= ?
                    GROUP BY month
                    ORDER BY month ASC
                    """,
                    (client_name, date_from),
                ).fetchall()

        labels = []
        rx_data = []
        tx_data = []
        for month_val, rx, tx in rows:
            labels.append(month_val)
            rx_data.append(rx or 0)
            tx_data.append(tx or 0)

        return jsonify({
            "client": client_name,
            "labels": labels,
            "rx_bytes": rx_data,
            "tx_bytes": tx_data,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/wg/client_chart")
@login_required
def api_wg_client_chart():
    client_name = request.args.get("client")
    period = request.args.get("period", "month")
    now = datetime.now()
    selected_date_from = (request.args.get("date_from") or "").strip()
    selected_date_to = (request.args.get("date_to") or "").strip()
    if not client_name:
        return jsonify({"error": "client parameter required"}), 400

    if period == "day":
        date_from = now.strftime("%Y-%m-%d")
        date_to = None
    elif period == "week":
        date_from = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        date_to = None
    elif period == "year":
        date_from = (now - timedelta(days=365)).strftime("%Y-%m-%d")
        date_to = None
    elif period == "custom":
        date_from_dt = parse_date_yyyy_mm_dd(selected_date_from)
        date_to_dt = parse_date_yyyy_mm_dd(selected_date_to)
        if date_from_dt and date_to_dt:
            if date_from_dt > date_to_dt:
                date_from_dt, date_to_dt = date_to_dt, date_from_dt
            date_from = date_from_dt.strftime("%Y-%m-%d")
            date_to = (date_to_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            date_to = None
    else:
        date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        date_to = None

    try:
        with sqlite3.connect(app.config["WG_STATS_PATH"]) as conn:
            if date_to:
                rows = conn.execute(
                    """
                    SELECT date,
                           SUM(received) as rx,
                           SUM(sent) as tx
                    FROM wg_daily_stats
                    WHERE client = ? AND date >= ? AND date < ?
                    GROUP BY date
                    ORDER BY date ASC
                    """,
                    (client_name, date_from, date_to),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT date,
                           SUM(received) as rx,
                           SUM(sent) as tx
                    FROM wg_daily_stats
                    WHERE client = ? AND date >= ?
                    GROUP BY date
                    ORDER BY date ASC
                    """,
                    (client_name, date_from),
                ).fetchall()

        labels = []
        rx_data = []
        tx_data = []
        for date_val, rx, tx in rows:
            labels.append(date_val)
            rx_data.append(rx or 0)
            tx_data.append(tx or 0)

        return jsonify({
            "client": client_name,
            "labels": labels,
            "rx_bytes": rx_data,
            "tx_bytes": tx_data,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
