import json
import os
import platform
import re

import psutil


BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)

ANTIZAPRET_SETUP_PATH = "/root/antizapret/setup"
STATUSOPENVPN_SETUP_PATH = os.path.join(BASE_DIR, "setup")
ENV_PATH = os.path.join(BASE_DIR, "src", ".env")
SETTINGS_PATH = os.path.join(BASE_DIR, "src", "settings.json")
SETUP_DESCRIPTIONS_PATH = os.path.join(BASE_DIR, "src", "setup_descriptions.json")
LEGACY_ADMIN_INFO_PATH = os.path.join(BASE_DIR, "src", "telegram_admins.json")

CACHE_DURATION = 5
MAX_CPU_HISTORY = 60 * 12
DB_SAVE_INTERVAL = 300
SAMPLE_INTERVAL = 10
MAX_HISTORY_SECONDS = 7 * 24 * 3600
LIVE_POINTS = 60

BOT_SERVICE_NAME = "telegram-bot"
GITHUB_REPO = "TheMurmabis/StatusOpenVPN"
UPDATE_SCRIPT = os.path.join(BASE_DIR, "scripts", "update_silent.sh")
UPDATE_LOG_PATH = "/tmp/statusopenvpn-update.log"

VPN_SYSTEMD_UNITS = (
    ("openvpn-server@antizapret-udp.service", "Antizapret UDP", "openvpn"),
    ("openvpn-server@antizapret-tcp.service", "Antizapret TCP", "openvpn"),
    ("openvpn-server@vpn-udp.service", "VPN UDP", "openvpn"),
    ("openvpn-server@vpn-tcp.service", "VPN TCP", "openvpn"),
    ("wg-quick@antizapret.service", "Antizapret", "wireguard"),
    ("wg-quick@vpn.service", "VPN", "wireguard"),
)

VPN_SYSTEMD_UNIT_SET = frozenset(u[0] for u in VPN_SYSTEMD_UNITS)

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

PROTOCOL_TO_SERVER_CONFIG = {
    "UDP": "/etc/openvpn/server/antizapret-udp.conf",
    "TCP": "/etc/openvpn/server/antizapret-tcp.conf",
    "VPN-UDP": "/etc/openvpn/server/vpn-udp.conf",
    "VPN-TCP": "/etc/openvpn/server/vpn-tcp.conf",
}

DEFAULT_SETTINGS = {
    "app_name": "StatusOpenVPN",
    "telegram_admins": {},
    "bot_enabled": False,
    "show_ovpn_menu": True,
    "show_wg_menu": True,
    "hide_ovpn_ip": True,
    "hide_wg_ip": True,
    "hide_wg_warp_interface": False,
    "stats_retention_days": 365,
    "history_max_records": 1000,
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

WG_CLIENT_CONFIG_DIRS = [
    ("/root/antizapret/client/wireguard/vpn", "vpn", "wg"),
    ("/root/antizapret/client/wireguard/antizapret", "antizapret", "wg"),
    ("/root/antizapret/client/amneziawg/vpn", "vpn", "am"),
    ("/root/antizapret/client/amneziawg/antizapret", "antizapret", "am"),
]

STATS_DB_CLEAR_OVPN_PHRASE = "OpenVPN"
STATS_DB_CLEAR_WG_PHRASE = "WireGuard"


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


def _load_setup_descriptions():
    with open(SETUP_DESCRIPTIONS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["web_setup"], data["antizapret_setup"]


WEB_SETUP_DESCRIPTIONS, ANTIZAPRET_SETUP_DESCRIPTIONS = _load_setup_descriptions()
