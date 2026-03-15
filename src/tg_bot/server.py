"""Функции мониторинга и статистики сервера."""

import asyncio
import datetime

from .utils import (
    get_color_by_percent,
    format_vpn_clients,
    parse_handshake_time,
    is_peer_online,
    read_wg_config,
)


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
    services = [
        ("StatusOpenVPN", "StatusOpenVPN.service"),
        ("Telegram bot", "telegram-bot.service"),
    ]
    lines = ["<b>⚙️ Службы StatusOpenVPN:</b>", ""]
    
    for label, service in services:
        state = await get_service_state(service)
        icon = "🟢" if state == "active" else "🔴" if state == "inactive" else "🟡"
        lines.append(f"{icon} <b>{label}:</b> {state}")
    
    return "\n".join(lines)


def _get_openvpn_online_clients():
    """Получить список онлайн-клиентов OpenVPN."""
    clients = set()
    file_paths = [
        "/etc/openvpn/server/logs/antizapret-udp-status.log",
        "/etc/openvpn/server/logs/antizapret-tcp-status.log",
        "/etc/openvpn/server/logs/vpn-udp-status.log",
        "/etc/openvpn/server/logs/vpn-tcp-status.log",
    ]
    
    for file_path in file_paths:
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                for line in file:
                    if not line.startswith("CLIENT_LIST"):
                        continue
                    parts = line.strip().split(",")
                    if len(parts) < 2:
                        continue
                    client_name = parts[1].strip()
                    if client_name:
                        clients.add(client_name)
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"Ошибка чтения {file_path}: {e}")
    
    return sorted(clients)


def _parse_wireguard_online_clients(output: str):
    """Разобрать вывод WireGuard для онлайн-клиентов."""
    online_clients = []
    lines = (output or "").splitlines()
    
    vpn_mapping = read_wg_config("/etc/wireguard/vpn.conf")
    antizapret_mapping = read_wg_config("/etc/wireguard/antizapret.conf")
    client_mapping = {**vpn_mapping, **antizapret_mapping}
    
    current_peer = None
    for line in lines:
        line = line.strip()
        if line.startswith("peer:"):
            current_peer = line.split(":", 1)[1].strip()
            continue
        if line.startswith("latest handshake:") and current_peer:
            handshake_raw = line.split(":", 1)[1].strip()
            handshake_time = parse_handshake_time(handshake_raw)
            if handshake_time and is_peer_online(handshake_time):
                online_clients.append(client_mapping.get(current_peer, current_peer))
            current_peer = None
    
    return sorted(set(online_clients))


async def get_wireguard_online_clients():
    """Получить список онлайн-клиентов WireGuard."""
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
        return _parse_wireguard_online_clients(stdout.decode())
    except Exception:
        return []


async def get_online_clients_text():
    """Получить отформатированный текст онлайн-клиентов."""
    openvpn_clients = _get_openvpn_online_clients()
    wg_clients = await get_wireguard_online_clients()
    
    lines = ["<b>👥 Кто онлайн:</b>", ""]
    
    if openvpn_clients:
        lines.append("<b>OpenVPN:</b>")
        lines.extend([f"• {client}" for client in openvpn_clients])
    else:
        lines.append("<b>OpenVPN:</b> нет активных клиентов")
    
    lines.append("")
    
    if wg_clients:
        lines.append("<b>WireGuard:</b>")
        lines.extend([f"• {client}" for client in wg_clients])
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
