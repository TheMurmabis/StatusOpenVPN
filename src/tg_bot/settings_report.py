"""Форматирование отчёта и сравнение настроек для импорта через Telegram."""

import json
from typing import Any

SETTINGS_KEY_LABELS = {
    "app_name": "Название приложения",
    "bot_enabled": "Бот включён",
    "show_ovpn_menu": "OpenVPN в меню",
    "show_wg_menu": "WireGuard в меню",
    "hide_ovpn_ip": "Скрывать IP OpenVPN",
    "hide_wg_ip": "Скрывать IP WireGuard",
    "hide_wg_warp_interface": "Скрывать WARP-интерфейс",
    "shorten_wg_filenames": "Короткие имена WG",
    "stats_retention_days": "Хранение статистики (дней)",
    "history_max_records": "Лимит истории OpenVPN",
    "telegram_admins": "Администраторы",
    "telegram_clients": "Клиенты бота",
    "tg_bot_banned_user_ids": "Заблокированные пользователи",
    "tg_bot_pending_requests": "Ожидающие запросы",
    "load_thresholds": "Пороги нагрузки",
    "vpn_service_monitoring_enabled": "Мониторинг VPN-служб",
    "vpn_monitored_services": "Отслеживаемые VPN-службы",
    "remote_server_monitoring_enabled": "Мониторинг удалённых серверов",
    "tg_bot_profile_seeded": "Профиль бота задан",
}

TELEGRAM_MESSAGE_LIMIT = 4096


def settings_are_equal(left: dict, right: dict) -> bool:
    return json.dumps(left, sort_keys=True, ensure_ascii=False) == json.dumps(
        right, sort_keys=True, ensure_ascii=False
    )


def _yes_no(value: Any) -> str:
    return "да" if value else "нет"


def _count_admins(value: Any) -> int:
    return len(value) if isinstance(value, dict) else 0


def _count_clients(value: Any) -> tuple[int, int]:
    if not isinstance(value, dict):
        return 0, 0
    users = len(value)
    bindings = 0
    for item in value.values():
        if not isinstance(item, dict):
            continue
        names = item.get("client_names")
        if isinstance(names, list):
            bindings += len(names)
    return users, bindings


def _count_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _count_monitored_services(value: Any) -> tuple[int, int]:
    if not isinstance(value, dict):
        return 0, 0
    enabled = sum(1 for item in value.values() if item)
    return len(value), enabled


def _format_thresholds(value: Any) -> str:
    if not isinstance(value, dict):
        return "—"
    cpu = value.get("cpu", "—")
    memory = value.get("memory", "—")
    return f"CPU {cpu}%, RAM {memory}%"


def _format_scalar(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return _yes_no(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f"«{value}»" if value else "—"
    return "…"


def _format_value_for_key(key: str, value: Any) -> str:
    if key == "telegram_admins":
        return str(_count_admins(value))
    if key == "telegram_clients":
        users, bindings = _count_clients(value)
        return f"{users} польз., {bindings} прив."
    if key == "tg_bot_banned_user_ids":
        return str(_count_list(value))
    if key == "tg_bot_pending_requests":
        return str(len(value)) if isinstance(value, dict) else "0"
    if key == "load_thresholds":
        return _format_thresholds(value)
    if key == "vpn_monitored_services":
        total, enabled = _count_monitored_services(value)
        return f"{enabled}/{total} включено"
    if isinstance(value, bool):
        return _yes_no(value)
    return _format_scalar(value)


def _key_label(key: str) -> str:
    return SETTINGS_KEY_LABELS.get(key, key)


def format_settings_report(data: dict, *, title: str = "📋 <b>Настройки</b>") -> str:
    lines = [title, ""]
    priority_keys = [
        "app_name",
        "bot_enabled",
        "telegram_admins",
        "telegram_clients",
        "tg_bot_banned_user_ids",
        "tg_bot_pending_requests",
        "show_ovpn_menu",
        "show_wg_menu",
        "hide_ovpn_ip",
        "hide_wg_ip",
        "hide_wg_warp_interface",
        "shorten_wg_filenames",
        "stats_retention_days",
        "history_max_records",
        "load_thresholds",
        "vpn_service_monitoring_enabled",
        "vpn_monitored_services",
        "remote_server_monitoring_enabled",
    ]
    shown = set()
    for key in priority_keys:
        if key not in data:
            continue
        shown.add(key)
        lines.append(f"• <b>{_key_label(key)}:</b> {_format_value_for_key(key, data.get(key))}")

    extra_keys = sorted(key for key in data.keys() if key not in shown)
    for key in extra_keys:
        lines.append(f"• <b>{_key_label(key)}:</b> {_format_value_for_key(key, data.get(key))}")

    return "\n".join(lines)


def format_settings_diff(current: dict, new: dict) -> str:
    lines = ["📝 <b>Отличия от текущих настроек:</b>", ""]
    for key in sorted(set(current) | set(new)):
        old_value = current.get(key)
        new_value = new.get(key)
        if old_value == new_value:
            continue
        old_text = _format_value_for_key(key, old_value)
        new_text = _format_value_for_key(key, new_value)
        if key not in current:
            lines.append(f"• <b>{_key_label(key)}:</b> добавлено ({new_text})")
        elif key not in new:
            lines.append(f"• <b>{_key_label(key)}:</b> удалено (было {old_text})")
        else:
            lines.append(f"• <b>{_key_label(key)}:</b> {old_text} → {new_text}")

    if len(lines) == 2:
        lines.append("• Есть отличия во вложенных полях")
    return "\n".join(lines)


def build_settings_import_message(
    current: dict,
    imported: dict,
    *,
    equal: bool,
    replaced: bool = False,
) -> str:
    if replaced:
        title = "📋 <b>Текущие настройки</b>"
        header = "✅ <b>Настройки заменены.</b>"
    elif equal:
        title = "📋 <b>Настройки из файла</b>"
        header = "✅ <b>Настройки совпадают с текущими.</b>"
    else:
        title = "📋 <b>Настройки из файла</b>"
        header = None

    report = format_settings_report(imported, title=title)
    if equal or replaced:
        return f"{header}\n\n{report}"

    diff = format_settings_diff(current, imported)
    return (
        f"{diff}\n\n"
        f"{report}\n\n"
        f"⚠️ <b>Заменить текущие настройки данными из файла?</b>"
    )


def truncate_telegram_text(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> str:
    if len(text) <= limit:
        return text
    suffix = "\n\n… (сообщение обрезано)"
    return text[: limit - len(suffix)] + suffix
