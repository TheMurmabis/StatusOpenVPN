import sqlite3
import subprocess
from datetime import datetime

from src.ui.extensions import app
from src.ui.utils.format_utils import (
    format_handshake_time,
    humanize_bytes,
    mask_ip,
    parse_bytes,
)
from src.ui.utils.time_utils import is_peer_online, parse_relative_time


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


def read_wg_config(file_path):
    """Считывает клиентские данные из конфигурационного файла WireGuard."""
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
        print(f"Конфигурационный файл {file_path} не найден.")

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
    """Включает или отключает пир в конфигурационном файле WireGuard."""
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
    """Получение ежедневной статистики WG."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(app.config["WG_STATS_PATH"])
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM wg_daily_stats WHERE date = ?", (today,))
    rows = cursor.fetchall()
    conn.close()
    return {(row["peer"], row["interface"]): row for row in rows}


def parse_wireguard_output(output, hide_ip=True, hide_warp=False):
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

    if hide_warp:
        stats = [
            interface_item
            for interface_item in stats
            if interface_item.get("interface", "").lower() != "warp"
        ]

    return stats
