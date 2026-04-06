"""Функции мониторинга и статистики сервера."""

import asyncio
import datetime
from typing import Optional, Tuple

from .utils import (
    get_color_by_percent,
    format_vpn_clients,
    parse_handshake_time,
    is_peer_online,
    read_wg_config,
)

VPN_MONITORED_SERVICES = [
    ("OpenVPN Antizapret UDP", "openvpn-server@antizapret-udp"),
    ("OpenVPN Antizapret TCP", "openvpn-server@antizapret-tcp"),
    ("OpenVPN VPN UDP", "openvpn-server@vpn-udp"),
    ("OpenVPN VPN TCP", "openvpn-server@vpn-tcp"),
    ("WireGuard Antizapret", "wg-quick@antizapret"),
    ("WireGuard VPN", "wg-quick@vpn"),
]


def _lazy_psutil():
    """Ленивый импорт psutil."""
    import psutil
    return psutil


async def get_server_stats():
    """Получить статистику сервера."""
    try:
        psutil = _lazy_psutil()
        
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        disk = psutil.disk_usage("/")
        disk_total = disk.total / (1024**3)
        disk_used = disk.used / (1024**3)
        
        uptime = _get_uptime()
        formatted_uptime = _format_uptime(uptime)
        main_interface = _get_main_interface()
        
        traffic_text = ""
        if main_interface:
            stats = psutil.net_io_counters(pernic=True).get(main_interface)
            if stats:
                traffic_text = f"\n<b>🌐 Трафик</b> {main_interface}: ⬇ {stats.bytes_recv / (1024**3):.2f} GB / ⬆ {stats.bytes_sent / (1024**3):.2f} GB"
        
        vpn_clients = _count_online_clients()
        clients_section = format_vpn_clients(vpn_clients)
        
        stats_text = f"""
<b>📊 Статистика сервера: </b>

{get_color_by_percent(cpu_percent)} <b>ЦП:</b> {cpu_percent:>5}%
{get_color_by_percent(memory_percent)} <b>ОЗУ:</b> {memory_percent:>5}%
<b>👥 Онлайн: </b> {clients_section}
<b>💿 Диск:</b> {disk_used:.1f}/{disk_total:.1f} GB
<b>⏱️ Uptime:</b> {formatted_uptime}{traffic_text}

"""
        return stats_text
    except Exception as e:
        return f"❌ Ошибка получения статистики: {str(e)}"


async def get_service_state(service_name: str) -> str:
    """Получить состояние службы systemd."""
    try:
        process = await asyncio.create_subprocess_exec(
            "/bin/systemctl",
            "is-active",
            service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        state = stdout.decode().strip()
        
        if state not in ("active", "inactive", "failed"):
            return "unknown"
        return state
    except Exception:
        return "unknown"


async def get_services_status_text():
    """Получить текст статуса служб."""
    lines = ["<b>⚙️ VPN-службы:</b>", ""]
    for label, service in VPN_MONITORED_SERVICES:
        state = await get_service_state(service)
        icon = "🟢" if state == "active" else "🔴" if state == "inactive" else "🟡"
        lines.append(f"{icon} <b>{label}:</b> {state}")
    lines.extend(["", "<b>⚙️ Службы StatusOpenVPN:</b>", ""])
    other = [
        ("StatusOpenVPN", "StatusOpenVPN.service"),
        ("Telegram bot", "telegram-bot.service"),
    ]
    for label, service in other:
        state = await get_service_state(service)
        icon = "🟢" if state == "active" else "🔴" if state == "inactive" else "🟡"
        lines.append(f"{icon} <b>{label}:</b> {state}")
    return "\n".join(lines)


async def restart_systemd_service(service_name: str) -> tuple[bool, str]:
    """Перезапустить unit systemd. Возвращает (успех по is-active после restart, текст статуса или ошибки)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "/bin/systemctl",
            "restart",
            service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = (stderr or b"").decode().strip() or f"код {proc.returncode}"
            return False, err
        state = await get_service_state(service_name)
        return state == "active", state
    except Exception as e:
        return False, str(e)


def _format_connected_dt(dt: Optional[datetime.datetime]) -> str:
    """Краткая строка времени для сообщения в Telegram."""
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")


def _get_openvpn_online_entries():
    """Онлайн-клиенты OpenVPN: имя, протокол (инстанс), время подключения."""
    file_paths = [
        ("/etc/openvpn/server/logs/antizapret-udp-status.log", "Antizapret UDP"),
        ("/etc/openvpn/server/logs/antizapret-tcp-status.log", "Antizapret TCP"),
        ("/etc/openvpn/server/logs/vpn-udp-status.log", "VPN UDP"),
        ("/etc/openvpn/server/logs/vpn-tcp-status.log", "VPN TCP"),
    ]
    entries = []
    for file_path, protocol in file_paths:
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                for line in file:
                    if not line.startswith("CLIENT_LIST"):
                        continue
                    parts = line.strip().split(",")
                    if len(parts) < 2:
                        continue
                    client_name = parts[1].strip()
                    if not client_name:
                        continue
                    connected = "—"
                    if len(parts) > 7:
                        try:
                            raw = parts[7].strip()
                            start_dt = datetime.datetime.strptime(
                                raw, "%Y-%m-%d %H:%M:%S"
                            )
                            connected = _format_connected_dt(start_dt)
                        except (ValueError, IndexError):
                            pass
                    entries.append(
                        {
                            "name": client_name,
                            "protocol": f"OpenVPN · {protocol}",
                            "connected": connected,
                        }
                    )
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"Ошибка чтения {file_path}: {e}")

    entries.sort(key=lambda x: (x["name"].lower(), x["protocol"]))
    return entries


def _wg_online_proto_and_name(
    public_key: str,
    iface: Optional[str],
    vpn_mapping: dict,
    antizapret_mapping: dict,
) -> Tuple[str, str]:
    """
    Подпись и имя для пира WireGuard.

    Главный критерий — интерфейс из `wg show` (фактический туннель), чтобы не
    путать VPN и Antizapret при дубликате одного PublicKey в обоих .conf.
    Если интерфейс не распознан — fallback по наличию ключа в конфигах.
    """
    n = (iface or "").strip().lower()

    def name_vpn_first() -> str:
        return (
            vpn_mapping.get(public_key)
            or antizapret_mapping.get(public_key)
            or public_key
        )

    def name_az_first() -> str:
        return (
            antizapret_mapping.get(public_key)
            or vpn_mapping.get(public_key)
            or public_key
        )

    if n == "vpn":
        return "WireGuard · VPN", name_vpn_first()
    if n == "antizapret":
        return "WireGuard · Antizapret", name_az_first()

    if public_key in vpn_mapping:
        return "WireGuard · VPN", name_vpn_first()
    if public_key in antizapret_mapping:
        return "WireGuard · Antizapret", name_az_first()
    return "WireGuard", public_key


def _parse_wireguard_online_entries(output: str):
    """Разобрать вывод `wg show` для онлайн-пиров с протоколом и временем handshake."""
    entries = []
    lines = (output or "").splitlines()

    vpn_mapping = read_wg_config("/etc/wireguard/vpn.conf")
    antizapret_mapping = read_wg_config("/etc/wireguard/antizapret.conf")

    current_peer = None
    current_interface: Optional[str] = None
    for line in lines:
        line = line.strip()
        if line.startswith("interface:"):
            current_interface = line.split(":", 1)[1].strip()
            continue
        if line.startswith("peer:"):
            current_peer = line.split(":", 1)[1].strip()
            continue
        if line.startswith("latest handshake:") and current_peer:
            handshake_raw = line.split(":", 1)[1].strip()
            handshake_time = parse_handshake_time(handshake_raw)
            if handshake_time and is_peer_online(handshake_time):
                proto, name = _wg_online_proto_and_name(
                    current_peer,
                    current_interface,
                    vpn_mapping,
                    antizapret_mapping,
                )
                entries.append(
                    {
                        "name": name,
                        "protocol": proto,
                        "connected": _format_connected_dt(handshake_time),
                    }
                )
            current_peer = None

    entries.sort(key=lambda x: (x["name"].lower(), x["protocol"]))
    return entries


async def _get_wireguard_online_entries():
    """Получить список онлайн-клиентов WireGuard с деталями."""
    try:
        process = await asyncio.create_subprocess_exec(
            "/usr/bin/wg",
            "show",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            return []
        return _parse_wireguard_online_entries(stdout.decode())
    except Exception:
        return []


def _format_online_line(entry: dict) -> str:
    """Одна строка списка «кто онлайн»."""
    return (
        f"• <b>{entry['name']}</b>\n"
        f"  <i>{entry['protocol']}</i> · с {entry['connected']}"
    )


async def get_online_clients_text():
    """Получить отформатированный текст онлайн-клиентов."""
    openvpn_entries = _get_openvpn_online_entries()
    wg_entries = await _get_wireguard_online_entries()

    lines = ["<b>👥 Кто онлайн:</b>", ""]

    if openvpn_entries:
        lines.append("<b>OpenVPN:</b>")
        lines.extend(_format_online_line(e) for e in openvpn_entries)
    else:
        lines.append("<b>OpenVPN:</b> нет активных клиентов")

    lines.append("")

    if wg_entries:
        lines.append("<b>WireGuard:</b>")
        lines.extend(_format_online_line(e) for e in wg_entries)
    else:
        lines.append("<b>WireGuard:</b> нет активных клиентов")

    return "\n".join(lines)


def _get_main_interface():
    """Получить основной сетевой интерфейс."""
    psutil = _lazy_psutil()
    interfaces = psutil.net_io_counters(pernic=True)
    
    if not interfaces:
        return None
    
    main_iface = max(
        interfaces.items(),
        key=lambda x: x[1].bytes_recv + x[1].bytes_sent
    )[0]
    
    return main_iface


def _get_uptime():
    """Получить строку времени работы системы."""
    import subprocess
    try:
        uptime = subprocess.check_output("/usr/bin/uptime -p", shell=True).decode().strip()
    except subprocess.CalledProcessError:
        uptime = "Не удалось получить время работы"
    return uptime


def _format_uptime(uptime_string):
    """Форматировать строку uptime на русский."""
    import re
    pattern = r"(?:(\d+)\s*years?|(\d+)\s*months?|(\d+)\s*weeks?|(\d+)\s*days?|(\d+)\s*hours?|(\d+)\s*minutes?)"
    
    years = months = weeks = days = hours = minutes = 0
    
    matches = re.findall(pattern, uptime_string)
    
    for match in matches:
        if match[0]:
            years = int(match[0])
        elif match[1]:
            months = int(match[1])
        elif match[2]:
            weeks = int(match[2])
        elif match[3]:
            days = int(match[3])
        elif match[4]:
            hours = int(match[4])
        elif match[5]:
            minutes = int(match[5])
    
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


def _count_online_clients():
    """Подсчитать онлайн-клиентов VPN."""
    import re
    import subprocess
    
    total_openvpn = 0
    results = {}
    
    file_paths = [
        ("/etc/openvpn/server/logs/antizapret-udp-status.log", "UDP"),
        ("/etc/openvpn/server/logs/antizapret-tcp-status.log", "TCP"),
        ("/etc/openvpn/server/logs/vpn-udp-status.log", "VPN-UDP"),
        ("/etc/openvpn/server/logs/vpn-tcp-status.log", "VPN-TCP"),
    ]
    
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
                    handshake_time = parse_handshake_time(handshake_str)
                    if handshake_time and is_peer_online(handshake_time):
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
