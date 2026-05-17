import csv
import os
import socket
import subprocess
from datetime import datetime, timedelta

from cryptography import x509
from cryptography.hazmat.backends import default_backend

from src.ui.constants import (
    CLIENT_CONNECT_BAN_CHECK_BLOCK,
    CLIENT_SH_PATH,
    OPENVPN_BANNED_CLIENTS_FILE,
    OPENVPN_CLIENT_CONNECT_SCRIPT,
    OPENVPN_CONFIG_PATHS,
    OPENVPN_KEYS_DIR,
    OPENVPN_KEYS_DISABLED_DIR,
    OPENVPN_SOCKETS,
    PROTOCOL_TO_SOCKET,
)
from src.ui.state import client_cache
from src.ui.utils.format_utils import (
    format_bytes,
    format_date,
    format_duration,
    normalize_real_address,
)
from src.ui.utils.openvpn_naming import extract_client_name_from_ovpn


def read_banned_clients():
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


def write_banned_clients(clients):
    ordered = sorted(set(clients), key=str.lower)
    with open(OPENVPN_BANNED_CLIENTS_FILE, "w", encoding="utf-8") as f:
        if ordered:
            f.write("\n".join(ordered) + "\n")


def ensure_client_connect_ban_check_block():
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
            rest = content[first_line_end + 1:]
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
                    client_name = extract_client_name_from_ovpn(filename)
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


def list_openvpn_client_crt_files(client_name):
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


def read_pem_cert_not_after_utc(path):
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


def get_openvpn_client_cert_expiry(client_name):
    """По всем .crt клиента возвращает минимальный срок (самый ранний) и подпись для UI."""
    paths = list_openvpn_client_crt_files(client_name)
    if not paths:
        return None, "—"
    earliest = None
    for path in paths:
        na = read_pem_cert_not_after_utc(path)
        if na is None:
            continue
        if earliest is None or na < earliest:
            earliest = na
    if earliest is None:
        return None, "—"
    return earliest, earliest.strftime("%d.%m.%Y")


def cert_days_left_fields(expiry_dt):
    """Подпись остатка до окончания сертификата."""
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


def count_openvpn_expiring_certs(days=30):
    now = datetime.utcnow()
    limit = now + timedelta(days=days)
    total = 0
    for client_name in get_all_openvpn_clients():
        expiry_dt, _ = get_openvpn_client_cert_expiry(client_name)
        if expiry_dt is not None and now < expiry_dt < limit:
            total += 1
    return total


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

                previous_data = client_cache.get(
                    client_name, {"received": 0, "sent": 0, "timestamp": current_time}
                )
                previous_received = previous_data["received"]
                previous_sent = previous_data["sent"]
                previous_time = previous_data["timestamp"]

                time_diff = (current_time - previous_time).total_seconds()
                if time_diff >= 30:
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

                client_cache[client_name] = {
                    "received": received,
                    "sent": sent,
                    "timestamp": current_time,
                }

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
                        max(download_speed, 0),
                        max(upload_speed, 0),
                    ]
                )

    return data, total_received, total_sent, None
