"""Управление конфигурацией Telegram-бота."""

import os
import json

_settings_cache = None
_settings_mtime = 0

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json")
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
CLIENT_MAPPING_KEY = "CLIENT_MAPPING"

ITEMS_PER_PAGE = 5
DEFAULT_CPU_ALERT_THRESHOLD = 80
DEFAULT_MEMORY_ALERT_THRESHOLD = 80
LOAD_CHECK_INTERVAL = 60
LOAD_ALERT_COOLDOWN = 30 * 60


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
    
    if not isinstance(data, dict):
        data = {}
    
    data.setdefault("telegram_admins", {})
    data.setdefault("telegram_clients", {})
    
    if not isinstance(data.get("telegram_admins"), dict):
        data["telegram_admins"] = {}
    if not isinstance(data.get("telegram_clients"), dict):
        data["telegram_clients"] = {}
    
    _settings_cache = data
    try:
        _settings_mtime = os.path.getmtime(SETTINGS_PATH)
    except OSError:
        _settings_mtime = 0
    
    return data.copy()


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


def get_client_mapping():
    """Получить привязку клиентов к ID Telegram."""
    env_values = read_env_values()
    raw_value = env_values.get(CLIENT_MAPPING_KEY, "")
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
        if telegram_id and client_name:
            mapping[telegram_id] = client_name
    return mapping


def get_client_name_for_user(user_id: int):
    """Получить имя клиента по ID пользователя Telegram."""
    return get_client_mapping().get(str(user_id))


def set_client_mapping(telegram_id: str, client_name: str):
    """Установить привязку клиента для пользователя Telegram."""
    client_map = get_client_mapping()
    client_map[str(telegram_id)] = client_name
    serialized = ",".join([f"{k}:{v}" for k, v in client_map.items()])
    update_env_values({CLIENT_MAPPING_KEY: serialized})


def remove_client_mapping(telegram_id: str):
    """Удалить привязку клиента для пользователя Telegram."""
    client_map = get_client_mapping()
    client_map.pop(str(telegram_id), None)
    serialized = ",".join([f"{k}:{v}" for k, v in client_map.items()])
    update_env_values({CLIENT_MAPPING_KEY: serialized})


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
