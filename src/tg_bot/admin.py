"""Функции управления администраторами."""

from .config import load_settings, save_settings


def update_admin_info(user):
    """Обновить данные администратора из объекта пользователя Telegram."""
    if not user:
        return
    
    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        admin_map = {}
    
    user_id = str(user.id)
    display_name = " ".join(
        [part for part in [user.first_name, user.last_name] if part]
    ).strip()
    username = (user.username or "").strip()
    
    existing = admin_map.get(user_id, {})
    if not display_name:
        display_name = existing.get("display_name", "")
    if not username:
        username = existing.get("username", "")
    notify_enabled = existing.get("notify_enabled", True)
    notify_load_enabled = existing.get("notify_load_enabled", True)
    notify_request_enabled = existing.get("notify_request_enabled", True)
    notify_vpn_service_enabled = existing.get("notify_vpn_service_enabled", True)
    
    admin_map[user_id] = {
        "display_name": display_name,
        "username": username,
        "notify_enabled": notify_enabled,
        "notify_load_enabled": notify_load_enabled,
        "notify_request_enabled": notify_request_enabled,
        "notify_vpn_service_enabled": notify_vpn_service_enabled,
    }
    data["telegram_admins"] = admin_map
    save_settings(data)


def is_admin_notification_enabled(user_id: int) -> bool:
    """Проверить, включены ли уведомления для администратора."""
    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        return True
    admin_entry = admin_map.get(str(user_id), {})
    if not isinstance(admin_entry, dict):
        return True
    return bool(admin_entry.get("notify_enabled", True))


def set_admin_notification(user_id: int, enabled: bool):
    """Включить или отключить уведомления для администратора."""
    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        admin_map = {}
    admin_entry = admin_map.get(str(user_id), {})
    if not isinstance(admin_entry, dict):
        admin_entry = {}
    admin_entry["notify_enabled"] = bool(enabled)
    admin_map[str(user_id)] = admin_entry
    data["telegram_admins"] = admin_map
    save_settings(data)


def is_admin_load_notification_enabled(user_id: int) -> bool:
    """Проверить, включены ли уведомления о нагрузке для администратора."""
    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        return True
    admin_entry = admin_map.get(str(user_id), {})
    if not isinstance(admin_entry, dict):
        return True
    return bool(admin_entry.get("notify_load_enabled", True))


def set_admin_load_notification(user_id: int, enabled: bool):
    """Включить или отключить уведомления о нагрузке для администратора."""
    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        admin_map = {}
    admin_entry = admin_map.get(str(user_id), {})
    if not isinstance(admin_entry, dict):
        admin_entry = {}
    admin_entry["notify_load_enabled"] = bool(enabled)
    admin_map[str(user_id)] = admin_entry
    data["telegram_admins"] = admin_map
    save_settings(data)


def is_admin_request_notification_enabled(user_id: int) -> bool:
    """Проверить, включены ли уведомления о запросах доступа для администратора."""
    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        return True
    admin_entry = admin_map.get(str(user_id), {})
    if not isinstance(admin_entry, dict):
        return True
    return bool(admin_entry.get("notify_request_enabled", True))


def set_admin_request_notification(user_id: int, enabled: bool):
    """Включить или отключить уведомления о запросах доступа для администратора."""
    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        admin_map = {}
    admin_entry = admin_map.get(str(user_id), {})
    if not isinstance(admin_entry, dict):
        admin_entry = {}
    admin_entry["notify_request_enabled"] = bool(enabled)
    admin_map[str(user_id)] = admin_entry
    data["telegram_admins"] = admin_map
    save_settings(data)


def is_any_admin_request_notification_enabled() -> bool:
    """Включены ли уведомления о запросах хотя бы у одного администратора из ADMIN_ID."""
    from .config import get_admin_ids

    for aid in get_admin_ids():
        if is_admin_request_notification_enabled(aid):
            return True
    return False


def is_admin_vpn_service_notification_enabled(user_id: int) -> bool:
    """Проверить, включены ли уведомления о VPN-службах для администратора."""
    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        return True
    admin_entry = admin_map.get(str(user_id), {})
    if not isinstance(admin_entry, dict):
        return True
    return bool(admin_entry.get("notify_vpn_service_enabled", True))


def set_admin_vpn_service_notification(user_id: int, enabled: bool):
    """Включить или отключить уведомления о VPN-службах для администратора."""
    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        admin_map = {}
    admin_entry = admin_map.get(str(user_id), {})
    if not isinstance(admin_entry, dict):
        admin_entry = {}
    admin_entry["notify_vpn_service_enabled"] = bool(enabled)
    admin_map[str(user_id)] = admin_entry
    data["telegram_admins"] = admin_map
    save_settings(data)


def get_user_label(telegram_id: str) -> str:
    """Получить отображаемую подпись для пользователя Telegram."""
    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        admin_map = {}
    entry = admin_map.get(str(telegram_id), {})
    if isinstance(entry, dict):
        username = (entry.get("username") or "").strip()
        if username:
            return f"@{username}"
    return str(telegram_id)
