import re

from src.ui.constants import ENV_PATH, PROTOCOL_TO_SERVER_CONFIG


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


def get_openvpn_server_ports():
    """Возвращает порты OpenVPN-серверов по метке протокола."""
    ports = {}
    for protocol, config_path in PROTOCOL_TO_SERVER_CONFIG.items():
        try:
            with open(config_path, "r", encoding="utf-8") as conf_file:
                for raw_line in conf_file:
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    match = re.match(r"^port\s+(\d+)\b", line)
                    if match:
                        ports[protocol] = match.group(1)
                        break
        except (FileNotFoundError, OSError):
            continue
    return ports
