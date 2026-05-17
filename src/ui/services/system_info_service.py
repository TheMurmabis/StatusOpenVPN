import json
import subprocess
import time
from datetime import datetime, timedelta

import psutil

from src.ui import state
from src.ui.constants import (
    CACHE_DURATION,
    DB_SAVE_INTERVAL,
    HOST_STATIC_INFO,
    MAX_CPU_HISTORY,
    MAX_HISTORY_SECONDS,
    SAMPLE_INTERVAL,
)
from src.ui.services.openvpn_service import (
    count_openvpn_expiring_certs,
    read_banned_clients,
)
from src.ui.services.settings_service import read_settings
from src.ui.services.stats_service import ensure_db, save_minute_average_to_db
from src.ui.services.vpn_service import get_vpn_systemd_states
from src.ui.services.wireguard_service import get_disabled_wg_peers
from src.ui.utils.format_utils import format_bytes, format_uptime
from src.ui.utils.network_utils import (
    get_default_interface,
    get_network_load,
    get_network_stats,
    get_uptime,
)
from src.ui.utils.time_utils import is_peer_online, parse_relative_time


def count_online_clients(file_paths):
    total_openvpn = 0
    results = {}

    hide_warp = bool(read_settings().get("hide_wg_warp_interface", False))
    try:
        wg_output = subprocess.check_output(["/usr/bin/wg", "show"], text=True)
        current_interface = ""
        online_wg = 0
        for raw_line in wg_output.splitlines():
            line = raw_line.strip()
            if line.startswith("interface:"):
                current_interface = line.split(":", 1)[1].strip().lower()
                continue
            if not line.startswith("latest handshake:"):
                continue
            if hide_warp and current_interface == "warp":
                continue

            handshake_str = line.split(":", 1)[1].strip()
            if handshake_str in {"0 seconds ago", "now", "Now"}:
                online_wg += 1
                continue
            try:
                handshake_time = parse_relative_time(handshake_str)
                if is_peer_online(handshake_time):
                    online_wg += 1
            except Exception:
                continue
        results["WireGuard"] = online_wg
    except Exception:
        results["WireGuard"] = 0

    for path, _ in file_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("CLIENT_LIST"):
                        total_openvpn += 1
        except Exception:
            continue

    results["OpenVPN"] = total_openvpn
    return results


def count_blocked_clients():
    try:
        openvpn_blocked = len(read_banned_clients())
    except OSError:
        openvpn_blocked = 0

    try:
        disabled_wg_peers = get_disabled_wg_peers()
        wireguard_blocked = sum(len(peers) for peers in disabled_wg_peers.values())
    except OSError:
        wireguard_blocked = 0

    return {"OpenVPN": openvpn_blocked, "WireGuard": wireguard_blocked}


def get_system_info():
    return state.cached_system_info


def update_system_info():
    file_paths = [
        ("/etc/openvpn/server/logs/antizapret-udp-status.log", "UDP"),
        ("/etc/openvpn/server/logs/antizapret-tcp-status.log", "TCP"),
        ("/etc/openvpn/server/logs/vpn-udp-status.log", "VPN-UDP"),
        ("/etc/openvpn/server/logs/vpn-tcp-status.log", "VPN-TCP"),
    ]

    while True:
        current_time = time.time()
        if not state.cached_system_info or (
            current_time - state.last_fetch_time >= CACHE_DURATION
        ):
            cpu_percent = psutil.cpu_percent(interval=1)
            ram_percent = psutil.virtual_memory().percent
            timestamp = datetime.now()

            state.cpu_history.append(
                {"timestamp": timestamp, "cpu": cpu_percent, "ram": ram_percent}
            )
            if len(state.cpu_history) > MAX_CPU_HISTORY:
                state.cpu_history.pop(0)

            interface = get_default_interface()
            network_stats = get_network_stats(interface) if interface else None
            vpn_clients = count_online_clients(file_paths)
            vpn_blocked = count_blocked_clients()
            openvpn_expiring_certs = count_openvpn_expiring_certs()
            vpn_services = get_vpn_systemd_states()

            _mem = psutil.virtual_memory()
            _disk = psutil.disk_usage("/")
            state.cached_system_info = {
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
                "vpn_blocked": vpn_blocked,
                "openvpn_expiring_certs": openvpn_expiring_certs,
                "vpn_services": vpn_services,
            }

            state.last_fetch_time = current_time

        time.sleep(CACHE_DURATION)


def update_system_info_loop():
    ensure_db()

    while True:
        now = time.time()
        if now - state.last_collect >= SAMPLE_INTERVAL:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            ts = datetime.now()
            state.cpu_history.append({"timestamp": ts, "cpu": cpu, "ram": ram})
            cutoff = datetime.now() - timedelta(seconds=MAX_HISTORY_SECONDS)
            while state.cpu_history and state.cpu_history[0]["timestamp"] < cutoff:
                state.cpu_history.pop(0)
            state.last_collect = now

        if now - state.last_db_save >= DB_SAVE_INTERVAL:
            save_minute_average_to_db()
            state.last_db_save = now

        time.sleep(1)


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

            if (rx + tx) > 0:
                interfaces.append(name)

        return interfaces

    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Ошибка при получении интерфейсов: {e}")
        return []


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
