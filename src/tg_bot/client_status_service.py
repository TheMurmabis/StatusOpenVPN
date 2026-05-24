import os
import sqlite3
import subprocess
import shutil
from datetime import datetime, timedelta

from src.config import Config
from src.ui.services.openvpn_service import (
    ensure_client_connect_ban_check_block,
    kick_openvpn_client,
    read_banned_clients,
    read_csv,
    write_banned_clients,
)
from src.ui.services.wireguard_service import (
    get_disabled_wg_peers,
    get_wireguard_stats,
    parse_wireguard_output,
    toggle_peer_config,
)
from src.ui.utils.format_utils import format_bytes


OPENVPN_LOGS = (
    ("/etc/openvpn/server/logs/antizapret-udp-status.log", "UDP"),
    ("/etc/openvpn/server/logs/antizapret-tcp-status.log", "TCP"),
    ("/etc/openvpn/server/logs/vpn-udp-status.log", "VPN-UDP"),
    ("/etc/openvpn/server/logs/vpn-tcp-status.log", "VPN-TCP"),
)


def get_client_statuses(vpn_type: str, clients: list[str]) -> dict[str, dict]:
    if vpn_type == "openvpn":
        return _get_openvpn_statuses(clients)
    return _get_wireguard_statuses(clients)


def get_client_brief(vpn_type: str, client_name: str) -> dict:
    statuses = get_client_statuses(vpn_type, [client_name])
    status = statuses.get(
        client_name,
        {"state": "offline", "online": False, "blocked": False},
    )
    stats = _get_openvpn_brief_stats(client_name) if vpn_type == "openvpn" else _get_wireguard_brief_stats(client_name)
    return {"status": status, "stats": stats}


def set_client_block(vpn_type: str, client_name: str, should_block: bool) -> tuple[bool, str]:
    if vpn_type == "openvpn":
        return _set_openvpn_client_block(client_name, should_block)
    return _set_wireguard_client_block(client_name, should_block)


def _get_openvpn_statuses(clients: list[str]) -> dict[str, dict]:
    online_names = set()
    for file_path, protocol in OPENVPN_LOGS:
        rows, _, _, _ = read_csv(file_path, protocol)
        for row in rows:
            name = row[0]
            if name and name != "UNDEF":
                online_names.add(name)

    blocked_names = read_banned_clients()
    statuses = {}
    for client in clients:
        blocked = client in blocked_names
        online = client in online_names and not blocked
        state = "blocked" if blocked else ("online" if online else "offline")
        statuses[client] = {"state": state, "online": online, "blocked": blocked}
    return statuses


def _get_wireguard_statuses(clients: list[str]) -> dict[str, dict]:
    stats = parse_wireguard_output(get_wireguard_stats(), hide_ip=True, hide_warp=False)
    disabled = get_disabled_wg_peers()
    online_map = {}
    for iface in stats:
        for peer in iface.get("peers", []):
            name = peer.get("client")
            if not name or name == "N/A":
                continue
            if peer.get("online"):
                online_map[name] = True
            elif name not in online_map:
                online_map[name] = False

    blocked_names = set()
    for peers in disabled.values():
        for peer in peers:
            name = peer.get("client")
            if name and name != "N/A":
                blocked_names.add(name)

    statuses = {}
    for client in clients:
        blocked = client in blocked_names
        online = bool(online_map.get(client, False)) and not blocked
        state = "blocked" if blocked else ("online" if online else "offline")
        statuses[client] = {"state": state, "online": online, "blocked": blocked}
    return statuses


def _get_openvpn_brief_stats(client_name: str) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    received = 0
    sent = 0
    last_connected = None
    with sqlite3.connect(Config.LOGS_DATABASE_PATH) as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(total_bytes_received), 0),
                COALESCE(SUM(total_bytes_sent), 0),
                MAX(last_connected)
            FROM daily_stats
            WHERE client_name = ? AND hour >= ? AND hour < ?
            """,
            (client_name, today, tomorrow),
        ).fetchone()
        if row:
            received = row[0] or 0
            sent = row[1] or 0
            last_connected = row[2]
    return {
        "today_received": format_bytes(received),
        "today_sent": format_bytes(sent),
        "last_activity": _format_activity(last_connected),
    }


def _get_wireguard_brief_stats(client_name: str) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    received = 0
    sent = 0
    last_activity = None
    with sqlite3.connect(Config.WG_STATS_PATH) as conn:
        daily = conn.execute(
            """
            SELECT
                COALESCE(SUM(received), 0),
                COALESCE(SUM(sent), 0)
            FROM wg_daily_stats
            WHERE client = ? AND date = ?
            """,
            (client_name, today),
        ).fetchone()
        if daily:
            received = daily[0] or 0
            sent = daily[1] or 0
        hour_row = conn.execute(
            """
            SELECT MAX(hour)
            FROM wg_hourly_stats
            WHERE client = ? AND substr(hour, 1, 10) = ?
            """,
            (client_name, today),
        ).fetchone()
        if hour_row:
            last_activity = hour_row[0]
    return {
        "today_received": format_bytes(received),
        "today_sent": format_bytes(sent),
        "last_activity": _format_activity(last_activity),
    }


def _set_openvpn_client_block(client_name: str, should_block: bool) -> tuple[bool, str]:
    try:
        ensure_client_connect_ban_check_block()
        banned_clients = read_banned_clients()
        if should_block:
            banned_clients.add(client_name)
            write_banned_clients(banned_clients)
            kick_openvpn_client(client_name, protocol=None)
            return True, "Клиент заблокирован."
        banned_clients.discard(client_name)
        write_banned_clients(banned_clients)
        return True, "Блокировка снята."
    except Exception as exc:
        return False, str(exc)


def _set_wireguard_client_block(client_name: str, should_block: bool) -> tuple[bool, str]:
    peers = _get_wireguard_client_peers(client_name)
    if not peers:
        return False, "Пиры клиента не найдены."

    target_enabled = not should_block
    to_change = [peer for peer in peers if peer["enabled"] != target_enabled]
    if not to_change:
        return True, "Состояние уже актуально."

    changed_interfaces = set()
    for peer in to_change:
        config_path = f"/etc/wireguard/{peer['interface']}.conf"
        if not os.path.exists(config_path):
            return False, f"Конфиг {config_path} не найден."
        success = toggle_peer_config(config_path, peer["peer"], target_enabled)
        if not success:
            return False, "Не удалось изменить конфигурацию пира."
        changed_interfaces.add(peer["interface"])

    ok, err = _sync_wireguard_interfaces(changed_interfaces)
    if not ok:
        return False, err

    return True, ("Клиент заблокирован." if should_block else "Блокировка снята.")


def _get_wireguard_client_peers(client_name: str) -> list[dict]:
    peers = []
    active_stats = parse_wireguard_output(get_wireguard_stats(), hide_ip=True, hide_warp=False)
    for iface in active_stats:
        iface_name = iface.get("interface")
        if not iface_name:
            continue
        for peer in iface.get("peers", []):
            if peer.get("client") == client_name:
                peers.append(
                    {
                        "interface": iface_name,
                        "peer": peer.get("peer"),
                        "enabled": True,
                    }
                )

    disabled_map = get_disabled_wg_peers()
    for iface_name, iface_peers in disabled_map.items():
        for peer in iface_peers:
            if peer.get("client") == client_name:
                peers.append(
                    {
                        "interface": iface_name,
                        "peer": peer.get("peer"),
                        "enabled": False,
                    }
                )

    unique = {}
    for peer in peers:
        key = (peer["interface"], peer["peer"])
        unique[key] = peer
    return list(unique.values())


def _sync_wireguard_interfaces(interfaces: set[str]) -> tuple[bool, str]:
    wg_quick = shutil.which("wg-quick") or "/usr/bin/wg-quick"
    wg_bin = shutil.which("wg") or "/usr/bin/wg"
    if not os.path.isfile(wg_quick):
        return False, "wg-quick не найден."
    if not os.path.isfile(wg_bin):
        return False, "wg не найден."

    for interface in interfaces:
        subprocess.run(
            ["/bin/bash", "-c", f"{wg_bin} syncconf {interface} <({wg_quick} strip {interface})"],
            check=True,
            env={**os.environ, "PATH": "/usr/bin:/bin"},
        )
    return True, ""


def _format_activity(value: str | None) -> str:
    if not value:
        return "—"
    val = str(value).strip().replace("T", " ")
    if len(val) >= 16:
        val = val[:16]
    return val
