"""Управление конфигурацией Telegram-бота."""

import os
import json

_settings_cache = None
_settings_mtime = 0

SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json"
)
ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
)
CLIENT_MAPPING_KEY = "CLIENT_MAPPING"
TG_BOT_PROFILE_SEEDED_KEY = "tg_bot_profile_seeded"
TG_BOT_PENDING_REQUESTS_KEY = "tg_bot_pending_requests"

ITEMS_PER_PAGE = 5
DEFAULT_CPU_ALERT_THRESHOLD = 80
DEFAULT_MEMORY_ALERT_THRESHOLD = 80
LOAD_CHECK_INTERVAL = 60
LOAD_ALERT_COOLDOWN = 30 * 60

VPN_SERVICE_CHECK_INTERVAL = 300
VPN_SERVICE_AUTORESTART_DELAY = 30
VPN_SERVICE_MONITOR_START_DELAY = 5


def get_bot_token():
    """Получить токен бота из окружения (ленивая загрузка)."""
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH)
    return os.getenv("BOT_TOKEN")


def get_admin_ids():
    """Получить ID администраторов из окружения (ленивая загрузка)."""
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH)
    raw = os.getenv("ADMIN_ID", "")
    return [int(x) for x in raw.split(",") if x.strip().isdigit()]


def normalize_settings_data(data):
    """Привести словарь настроек к ожидаемой структуре."""
    if not isinstance(data, dict):
        data = {}

    data.setdefault("telegram_admins", {})
    data.setdefault("telegram_clients", {})
    data.setdefault("tg_bot_banned_user_ids", [])

    if not isinstance(data.get("telegram_admins"), dict):
        data["telegram_admins"] = {}
    if not isinstance(data.get("telegram_clients"), dict):
        data["telegram_clients"] = {}
    bans = data.get("tg_bot_banned_user_ids")
    if not isinstance(bans, list):
        data["tg_bot_banned_user_ids"] = []
    pending = data.get(TG_BOT_PENDING_REQUESTS_KEY)
    if not isinstance(pending, dict):
        data[TG_BOT_PENDING_REQUESTS_KEY] = {}

    return data


def load_settings():
    """Загрузить настройки из JSON-файла (с кэшированием)."""
    global _settings_cache, _settings_mtime

    try:
        current_mtime = os.path.getmtime(SETTINGS_PATH)
        if _settings_cache is not None and current_mtime == _settings_mtime:
            return _settings_cache.copy()
    except OSError:
        pass

    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    data = normalize_settings_data(data)

    _settings_cache = data
    try:
        _settings_mtime = os.path.getmtime(SETTINGS_PATH)
    except OSError:
        _settings_mtime = 0

    return data.copy()


def is_tg_bot_profile_seeded() -> bool:
    """Уже выполнялась однократная установка описания и «о боте» через API."""
    return bool(load_settings().get(TG_BOT_PROFILE_SEEDED_KEY))


def mark_tg_bot_profile_seeded() -> None:
    """Пометить, что описание и «о боте» заданы (чтобы не перезаписывать при каждом запуске)."""
    data = load_settings()
    data[TG_BOT_PROFILE_SEEDED_KEY] = True
    save_settings(data)


def save_settings(data):
    """Сохранить настройки в JSON-файл."""
    global _settings_cache, _settings_mtime

    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        f.write("\n")

    _settings_cache = data.copy()
    try:
        _settings_mtime = os.path.getmtime(SETTINGS_PATH)
    except OSError:
        _settings_mtime = 0


def read_env_values():
    """Прочитать все значения из файла .env."""
    values = {}
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except FileNotFoundError:
        pass
    return values


def update_env_values(updates):
    """Обновить значения в файле .env."""
    updates = {k: v for k, v in updates.items() if k}
    if not updates:
        return

    updated_keys = set()
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
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

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def _normalize_client_names(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    normalized = []
    seen = set()
    for item in raw:
        name = str(item).strip()
        if not name or name in seen:
            continue
        normalized.append(name)
        seen.add(name)
    return normalized


def _parse_env_client_mapping_multi() -> dict[str, list[str]]:
    env_values = read_env_values()
    raw_value = (env_values.get(CLIENT_MAPPING_KEY) or "").strip()
    mapping = {}
    if not raw_value:
        return mapping
    for item in raw_value.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        telegram_id, client_name = item.split(":", 1)
        telegram_id = telegram_id.strip()
        client_name = client_name.strip()
        if not telegram_id or not client_name:
            continue
        names = mapping.setdefault(telegram_id, [])
        if client_name not in names:
            names.append(client_name)
    return mapping


def _normalize_settings_client_mapping(raw_clients: dict) -> dict[str, list[str]]:
    normalized = {}
    if not isinstance(raw_clients, dict):
        return normalized
    for telegram_id, client_data in raw_clients.items():
        tid = str(telegram_id).strip()
        if not tid:
            continue
        names = []
        if isinstance(client_data, dict):
            if "client_names" in client_data:
                names = _normalize_client_names(client_data.get("client_names"))
            elif "client_name" in client_data:
                single_name = str(client_data.get("client_name") or "").strip()
                if single_name:
                    names = [single_name]
            elif "name" in client_data:
                legacy_name = str(client_data.get("name") or "").strip()
                if legacy_name:
                    names = [legacy_name]
        elif isinstance(client_data, str):
            single_name = client_data.strip()
            if single_name:
                names = [single_name]
        if names:
            normalized[tid] = names
    return normalized


def _write_client_mapping_to_settings(
    mapping: dict[str, list[str]], preserve_allowed_protocols: bool = True
):
    data = load_settings()
    clients = data.get("telegram_clients") or {}
    if not isinstance(clients, dict):
        clients = {}
    next_clients = {}
    for telegram_id, names in mapping.items():
        normalized_names = _normalize_client_names(names)
        if not normalized_names:
            continue
        prev = clients.get(telegram_id, {}) if preserve_allowed_protocols else {}
        if not isinstance(prev, dict):
            prev = {}
        next_clients[telegram_id] = {
            "allowed_protocols": prev.get("allowed_protocols", {}),
            "client_names": normalized_names,
        }
    for telegram_id, prev in clients.items():
        if telegram_id in next_clients:
            continue
        if not isinstance(prev, dict):
            continue
        allowed = prev.get("allowed_protocols")
        if isinstance(allowed, dict):
            next_clients[telegram_id] = {"allowed_protocols": allowed, "client_names": []}
    data["telegram_clients"] = next_clients
    save_settings(data)


def migrate_client_mapping_from_env_if_needed():
    data = load_settings()
    clients = data.get("telegram_clients") or {}
    if not isinstance(clients, dict):
        clients = {}
    normalized = _normalize_settings_client_mapping(clients)
    env_mapping = _parse_env_client_mapping_multi()
    changed = False

    for telegram_id, names in env_mapping.items():
        existing = normalized.get(telegram_id, [])
        merged = existing[:]
        for name in names:
            if name not in merged:
                merged.append(name)
        if merged != existing:
            normalized[telegram_id] = merged
            changed = True

    if changed:
        _write_client_mapping_to_settings(normalized, preserve_allowed_protocols=True)
    elif normalized != _normalize_settings_client_mapping(clients):
        _write_client_mapping_to_settings(normalized, preserve_allowed_protocols=True)

    if env_mapping:
        update_env_values({CLIENT_MAPPING_KEY: ""})


def get_client_mapping():
    """Получить привязку клиентов к ID Telegram (один ID -> список клиентов)."""
    migrate_client_mapping_from_env_if_needed()
    data = load_settings()
    clients = data.get("telegram_clients") or {}
    return _normalize_settings_client_mapping(clients)


def get_client_mapping_entries() -> list[tuple[str, str]]:
    entries = []
    for telegram_id, names in get_client_mapping().items():
        for name in names:
            entries.append((telegram_id, name))
    entries.sort(key=lambda item: (item[0], item[1].lower()))
    return entries


def get_client_names_for_user(user_id: int) -> list[str]:
    """Получить список клиентов по ID пользователя Telegram."""
    return get_client_mapping().get(str(user_id), [])


def get_client_name_for_user(user_id: int):
    """Получить первое имя клиента по ID пользователя Telegram."""
    names = get_client_names_for_user(user_id)
    return names[0] if names else None


def set_client_mapping(telegram_id: str, client_name: str):
    """Добавить привязку клиента для пользователя Telegram."""
    add_client_mapping(telegram_id, client_name)


def add_client_mapping(telegram_id: str, client_name: str):
    """Добавить привязку клиента для пользователя Telegram."""
    telegram_id = str(telegram_id).strip()
    client_name = str(client_name).strip()
    if not telegram_id or not client_name:
        return
    client_map = get_client_mapping()
    names = client_map.setdefault(telegram_id, [])
    if client_name not in names:
        names.append(client_name)
    _write_client_mapping_to_settings(client_map, preserve_allowed_protocols=True)
    remove_pending_access_request(telegram_id)


def remove_client_mapping(telegram_id: str, client_name: str = None):
    """Удалить одну или все привязки клиента для пользователя Telegram."""
    client_map = get_client_mapping()
    tid = str(telegram_id).strip()
    if not tid:
        return
    if client_name is None:
        client_map.pop(tid, None)
    else:
        target = str(client_name).strip()
        names = client_map.get(tid, [])
        names = [name for name in names if name != target]
        if names:
            client_map[tid] = names
        else:
            client_map.pop(tid, None)
    _write_client_mapping_to_settings(client_map, preserve_allowed_protocols=True)


def get_banned_user_ids() -> set[int]:
    """Множество Telegram user id, для которых бот не обрабатывает обновления."""
    data = load_settings()
    raw = data.get("tg_bot_banned_user_ids") or []
    if not isinstance(raw, list):
        return set()
    out: set[int] = set()
    for x in raw:
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            continue
    return out


def is_user_allowed_for_bot(user_id: int) -> bool:
    """Можно обрабатывать обновления: админ, привязанный клиент, либо админы ещё не заданы (первичная настройка)."""
    admin_ids = get_admin_ids()
    if not admin_ids:
        return True
    uid = int(user_id)
    if uid in admin_ids:
        return True
    if get_client_names_for_user(uid):
        return True
    return False


def is_user_banned(user_id: int) -> bool:
    """Проверить, заблокирован ли пользователь для взаимодействия с ботом."""
    return int(user_id) in get_banned_user_ids()


def ban_user(user_id: int) -> None:
    """Добавить пользователя в бан-лист бота."""
    uid = int(user_id)
    data = load_settings()
    bans = data.get("tg_bot_banned_user_ids") or []
    if not isinstance(bans, list):
        bans = []
    if uid not in bans:
        bans.append(uid)
    data["tg_bot_banned_user_ids"] = sorted(bans)
    save_settings(data)
    remove_pending_access_request(str(uid))


def get_pending_access_requests() -> dict[str, dict]:
    data = load_settings()
    raw = data.get(TG_BOT_PENDING_REQUESTS_KEY) or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for key, value in raw.items():
        tid = str(key).strip()
        if not tid.isdigit() or not isinstance(value, dict):
            continue
        out[tid] = value
    return out


def get_pending_request_user_ids() -> list[str]:
    return sorted(get_pending_access_requests().keys(), key=int)


def get_pending_requests_count() -> int:
    return len(get_pending_access_requests())


def upsert_pending_access_request(
    user_id: int,
    *,
    display_name: str = "",
    username: str = "",
    suggested_name: str = "",
) -> None:
    tid = str(int(user_id))
    data = load_settings()
    pending = data.get(TG_BOT_PENDING_REQUESTS_KEY) or {}
    if not isinstance(pending, dict):
        pending = {}
    entry = pending.get(tid, {})
    if not isinstance(entry, dict):
        entry = {}
    if display_name:
        entry["display_name"] = display_name
    if username:
        entry["username"] = username
    if suggested_name:
        entry["suggested_name"] = suggested_name
    pending[tid] = entry
    data[TG_BOT_PENDING_REQUESTS_KEY] = pending
    save_settings(data)


def remove_pending_access_request(telegram_id: str | int) -> None:
    tid = str(telegram_id).strip()
    if not tid:
        return
    data = load_settings()
    pending = data.get(TG_BOT_PENDING_REQUESTS_KEY) or {}
    if not isinstance(pending, dict) or tid not in pending:
        return
    pending = dict(pending)
    pending.pop(tid, None)
    data[TG_BOT_PENDING_REQUESTS_KEY] = pending
    save_settings(data)


def get_clientmap_selectable_user_ids() -> list[str]:
    mapping = get_client_mapping()
    pending = get_pending_access_requests()
    return sorted(set(mapping.keys()) | set(pending.keys()), key=int)


def unban_user(user_id: int) -> None:
    """Убрать пользователя из бан-листа бота."""
    uid = int(user_id)
    data = load_settings()
    bans = data.get("tg_bot_banned_user_ids") or []
    if not isinstance(bans, list):
        bans = []
    bans = [x for x in bans if int(x) != uid]
    data["tg_bot_banned_user_ids"] = sorted(set(int(x) for x in bans))
    save_settings(data)


def get_load_thresholds():
    """Получить пороги оповещения по CPU и памяти."""
    data = load_settings()
    thresholds = data.get("load_thresholds") or {}
    if not isinstance(thresholds, dict):
        thresholds = {}
    cpu = thresholds.get("cpu", DEFAULT_CPU_ALERT_THRESHOLD)
    memory = thresholds.get("memory", DEFAULT_MEMORY_ALERT_THRESHOLD)
    return cpu, memory


def set_load_thresholds(cpu_threshold: int = None, memory_threshold: int = None):
    """Установить пороги оповещения по CPU и/или памяти."""
    data = load_settings()
    thresholds = data.get("load_thresholds") or {}
    if not isinstance(thresholds, dict):
        thresholds = {}
    if cpu_threshold is not None:
        thresholds["cpu"] = int(cpu_threshold)
    if memory_threshold is not None:
        thresholds["memory"] = int(memory_threshold)
    data["load_thresholds"] = thresholds
    save_settings(data)


def is_vpn_monitoring_enabled() -> bool:
    """Глобальный переключатель фонового мониторинга VPN-служб."""
    data = load_settings()
    return bool(data.get("vpn_service_monitoring_enabled", True))


def set_vpn_monitoring_enabled(enabled: bool):
    """Включить или отключить фоновый мониторинг VPN-служб."""
    data = load_settings()
    data["vpn_service_monitoring_enabled"] = bool(enabled)
    save_settings(data)


def is_vpn_service_monitored(service_unit: str) -> bool:
    """Проверить, включён ли мониторинг VPN-службы."""
    if not is_vpn_monitoring_enabled():
        return False
    data = load_settings()
    monitored = data.get("vpn_monitored_services") or {}
    if not isinstance(monitored, dict):
        return True
    return bool(monitored.get(service_unit, True))


def set_vpn_service_monitored(service_unit: str, enabled: bool):
    """Включить или отключить мониторинг VPN-службы."""
    data = load_settings()
    monitored = data.get("vpn_monitored_services") or {}
    if not isinstance(monitored, dict):
        monitored = {}
    monitored[service_unit] = bool(enabled)
    data["vpn_monitored_services"] = monitored
    save_settings(data)


def get_client_allowed_protocols(telegram_id: str) -> dict:
    """Получить доступные протоколы для клиента. По умолчанию все включены."""
    default_protocols = {
        "openvpn_vpn": True,
        "openvpn_antizapret": True,
        "wireguard_vpn": True,
        "wireguard_antizapret": True,
        "openvpn_default": True,
        "openvpn_tcp": True,
        "openvpn_udp": True,
        "wireguard_wg": True,
        "wireguard_am": True,
    }
    data = load_settings()
    clients = data.get("telegram_clients") or {}
    if not isinstance(clients, dict):
        return default_protocols
    client_data = clients.get(str(telegram_id), {})
    if not isinstance(client_data, dict):
        return default_protocols
    protocols = client_data.get("allowed_protocols", {})
    if not isinstance(protocols, dict):
        return default_protocols

    # Поддержка старого формата (openvpn/wireguard) для обратной совместимости
    if "openvpn" in protocols or "wireguard" in protocols:
        openvpn_enabled = protocols.get("openvpn", True)
        wireguard_enabled = protocols.get("wireguard", True)
        return {
            "openvpn_vpn": openvpn_enabled,
            "openvpn_antizapret": openvpn_enabled,
            "wireguard_vpn": wireguard_enabled,
            "wireguard_antizapret": wireguard_enabled,
            "openvpn_default": True,
            "openvpn_tcp": True,
            "openvpn_udp": True,
            "wireguard_wg": True,
            "wireguard_am": True,
        }

    return {
        "openvpn_vpn": protocols.get("openvpn_vpn", True),
        "openvpn_antizapret": protocols.get("openvpn_antizapret", True),
        "wireguard_vpn": protocols.get("wireguard_vpn", True),
        "wireguard_antizapret": protocols.get("wireguard_antizapret", True),
        "openvpn_default": protocols.get("openvpn_default", True),
        "openvpn_tcp": protocols.get("openvpn_tcp", True),
        "openvpn_udp": protocols.get("openvpn_udp", True),
        "wireguard_wg": protocols.get("wireguard_wg", True),
        "wireguard_am": protocols.get("wireguard_am", True),
    }


def set_client_allowed_protocols(
    telegram_id: str,
    openvpn_vpn: bool = None,
    openvpn_antizapret: bool = None,
    wireguard_vpn: bool = None,
    wireguard_antizapret: bool = None,
    openvpn_default: bool = None,
    openvpn_tcp: bool = None,
    openvpn_udp: bool = None,
    wireguard_wg: bool = None,
    wireguard_am: bool = None,
):
    """Установить доступные протоколы для клиента."""
    data = load_settings()
    clients = data.get("telegram_clients") or {}
    if not isinstance(clients, dict):
        clients = {}
    current = get_client_allowed_protocols(telegram_id)
    client_data = clients.get(str(telegram_id), {})
    if not isinstance(client_data, dict):
        client_data = {}
    client_data["allowed_protocols"] = {
        "openvpn_vpn": current["openvpn_vpn"] if openvpn_vpn is None else bool(openvpn_vpn),
        "openvpn_antizapret": current["openvpn_antizapret"] if openvpn_antizapret is None else bool(openvpn_antizapret),
        "wireguard_vpn": current["wireguard_vpn"] if wireguard_vpn is None else bool(wireguard_vpn),
        "wireguard_antizapret": current["wireguard_antizapret"] if wireguard_antizapret is None else bool(wireguard_antizapret),
        "openvpn_default": current["openvpn_default"] if openvpn_default is None else bool(openvpn_default),
        "openvpn_tcp": current["openvpn_tcp"] if openvpn_tcp is None else bool(openvpn_tcp),
        "openvpn_udp": current["openvpn_udp"] if openvpn_udp is None else bool(openvpn_udp),
        "wireguard_wg": current["wireguard_wg"] if wireguard_wg is None else bool(wireguard_wg),
        "wireguard_am": current["wireguard_am"] if wireguard_am is None else bool(wireguard_am),
    }
    clients[str(telegram_id)] = client_data
    data["telegram_clients"] = clients
    save_settings(data)
