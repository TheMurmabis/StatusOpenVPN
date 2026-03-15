"""Вспомогательные функции для Telegram-бота."""

import os
import asyncio
import datetime
import re

_server_ip_cache = None


def get_external_ip():
    """Получить внешний IP-адрес (с кэшированием)."""
    global _server_ip_cache
    if _server_ip_cache is not None:
        return _server_ip_cache
    
    import requests
    try:
        response = requests.get("https://api.ipify.org", timeout=10)
        if response.status_code == 200:
            _server_ip_cache = response.text
            return _server_ip_cache
        return "IP не найден"
    except requests.Timeout:
        return "Ошибка: запрос превысил время ожидания."
    except requests.ConnectionError:
        return "Ошибка: нет подключения к интернету."
    except requests.RequestException as e:
        return f"Ошибка при запросе: {e}"


async def execute_script(option: str, client_name: str = None, days: str = None):
    """Выполнить shell-скрипт управления VPN."""
    script_path = "/root/antizapret/client.sh"
    
    if not os.path.exists(script_path):
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": f"❌ Файл {script_path} не найден! Убедитесь, что скрипт client.sh существует.",
        }
    
    command = f"{script_path} {option}"
    if option not in ["8", "7"] and client_name:
        command += f" {client_name}"
        if days and option == "1":
            command += f" {days}"
    
    try:
        env = os.environ.copy()
        env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        
        stdout, stderr = await process.communicate()
        return {
            "returncode": process.returncode,
            "stdout": stdout.decode().strip(),
            "stderr": stderr.decode().strip(),
        }
    except Exception as e:
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": f"❌ Ошибка при выполнении скрипта: {str(e)}",
        }


async def get_clients(vpn_type: str):
    """Получить список клиентов VPN."""
    option = "3" if vpn_type == "openvpn" else "6"
    result = await execute_script(option)
    
    if result["returncode"] == 0:
        clients = [
            c.strip()
            for c in result["stdout"].split("\n")
            if c.strip()
            and not c.startswith("OpenVPN client names:")
            and not c.startswith("WireGuard/AmneziaWG client names:")
            and not c.startswith("OpenVPN - List clients")
            and not c.startswith("WireGuard/AmneziaWG - List clients")
        ]
        return clients
    return []


async def get_all_clients_unique():
    """Объединённый отсортированный список уникальных имён клиентов (OpenVPN + WireGuard)."""
    ovpn = await get_clients("openvpn")
    wg = await get_clients("wireguard")
    return sorted(set(ovpn) | set(wg))


async def cleanup_openvpn_files(client_name: str):
    """Удалить файлы OpenVPN после удаления клиента."""
    clean_name = client_name.replace("antizapret-", "").replace("vpn-", "")
    
    dirs_to_check = [
        "/root/antizapret/client/openvpn/antizapret/",
        "/root/antizapret/client/openvpn/antizapret-tcp/",
        "/root/antizapret/client/openvpn/antizapret-udp/",
        "/root/antizapret/client/openvpn/vpn/",
        "/root/antizapret/client/openvpn/vpn-tcp/",
        "/root/antizapret/client/openvpn/vpn-udp/",
    ]
    
    deleted_files = []
    
    for dir_path in dirs_to_check:
        if not os.path.exists(dir_path):
            continue
        
        for filename in os.listdir(dir_path):
            if clean_name in filename:
                try:
                    file_path = os.path.join(dir_path, filename)
                    os.remove(file_path)
                    deleted_files.append(file_path)
                except Exception as e:
                    print(f"Ошибка удаления {file_path}: {e}")
    
    return deleted_files


def get_color_by_percent(percent):
    """Вернуть эмодзи-цвет по проценту."""
    if percent < 50:
        return "🟢"
    elif percent < 80:
        return "🟡"
    else:
        return "🔴"


def format_vpn_clients(clients_dict):
    """Форматировать словарь клиентов VPN в строку."""
    total = clients_dict['WireGuard'] + clients_dict['OpenVPN']
    
    if total == 0:
        return "0 шт."
    
    return f"""
├ <b>WireGuard:</b> {clients_dict['WireGuard']} шт.
└ <b>OpenVPN:</b> {clients_dict['OpenVPN']} шт."""


def parse_handshake_time(raw_value: str):
    """Разобрать строку времени handshake WireGuard."""
    value = (raw_value or "").strip()
    if not value:
        return None
    if value.lower() == "now":
        return datetime.datetime.now()
    if value.lower() in ["never", "n/a", "(none)"]:
        return None
    
    if any(unit in value for unit in ["мин", "час", "сек", "minute", "hour", "second", "day", "week"]):
        return _parse_relative_time(value)
    
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _parse_relative_time(relative_time):
    """Преобразовать строку относительного времени в datetime."""
    now = datetime.datetime.now()
    time_deltas = {"days": 0, "hours": 0, "minutes": 0, "seconds": 0}
    
    parts = relative_time.split()
    i = 0
    while i < len(parts):
        try:
            value = int(parts[i])
            unit = parts[i + 1]
            if "д" in unit or "day" in unit:
                time_deltas["days"] += value
            elif "ч" in unit or "hour" in unit:
                time_deltas["hours"] += value
            elif "мин" in unit or "minute" in unit:
                time_deltas["minutes"] += value
            elif "сек" in unit or "second" in unit:
                time_deltas["seconds"] += value
            i += 2
        except (ValueError, IndexError):
            break
    
    delta = datetime.timedelta(
        days=time_deltas["days"],
        hours=time_deltas["hours"],
        minutes=time_deltas["minutes"],
        seconds=time_deltas["seconds"],
    )
    
    return now - delta


def is_peer_online(last_handshake):
    """Проверить, онлайн ли пир WireGuard."""
    if not last_handshake:
        return False
    return datetime.datetime.now() - last_handshake < datetime.timedelta(minutes=3)


def read_wg_config(file_path):
    """Прочитать привязку клиентов из конфига WireGuard."""
    client_mapping = {}
    
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            current_client_name = None
            
            for line in file:
                line = line.strip()
                
                if line.startswith("# Client ="):
                    current_client_name = line.split("=", 1)[1].strip()
                elif line.startswith("[Peer]"):
                    current_client_name = current_client_name or "N/A"
                elif line.startswith("PublicKey =") and current_client_name:
                    public_key = line.split("=", 1)[1].strip()
                    client_mapping[public_key] = current_client_name
    except FileNotFoundError:
        pass
    
    return client_mapping


def find_config_file(dir_path: str, pattern) -> str:
    """Найти файл конфигурации по шаблону в каталоге."""
    if not os.path.exists(dir_path):
        return None
    
    for filename in os.listdir(dir_path):
        if pattern.fullmatch(filename):
            return os.path.join(dir_path, filename)
    
    return None
