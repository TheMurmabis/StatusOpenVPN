"""Построители клавиатур для Telegram-бота."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import (
    ITEMS_PER_PAGE,
    get_client_mapping,
    get_client_mapping_entries,
    get_clientmap_selectable_user_ids,
    get_load_thresholds,
    get_pending_access_requests,
    get_pending_request_user_ids,
    get_pending_requests_count,
    is_vpn_monitoring_enabled,
    is_vpn_service_monitored,
)
from .admin import (
    is_admin_notification_enabled,
    is_admin_load_notification_enabled,
    is_admin_request_notification_enabled,
    is_admin_vpn_service_notification_enabled,
    get_user_label,
)


def create_main_menu(server_ip: str):
    """Создать клавиатуру главного меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"ℹ️ Меню сервера: {server_ip}", callback_data="server_menu"
                ),
            ],
            [
                InlineKeyboardButton(text="OpenVPN", callback_data="openvpn_menu"),
                InlineKeyboardButton(text="WireGuard", callback_data="wireguard_menu"),
            ],
            [
                InlineKeyboardButton(text="🔄 Пересоздать файлы", callback_data="7"),
                InlineKeyboardButton(text="📦 Создать бэкап", callback_data="backups_menu"),
            ],
            [
                InlineKeyboardButton(
                    text="👥 Клиенты бота", callback_data="clients_menu"
                ),
                InlineKeyboardButton(
                    text="👤 Администраторы", callback_data="admins_menu"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔔 Уведомления", callback_data="notifications_menu"
                ),
            ],
        ]
    )


def create_backups_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📦 Бэкап клиентов",
                    callback_data="backup_vpn",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 StatusOpenVPN",
                    callback_data="backup_statusopenvpn",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Файл настроек",
                    callback_data="backup_settings",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")],
        ]
    )


def create_vpn_services_menu():
    """Создать меню выбора VPN сервиса."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="OpenVPN", callback_data="openvpn_menu"),
                InlineKeyboardButton(text="WireGuard", callback_data="wireguard_menu"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"),
            ],
        ]
    )


def create_server_menu():
    """Создать меню управления сервером."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Статистика", callback_data="server_stats"
                ),
                InlineKeyboardButton(
                    text="🔄 Перезагрузка", callback_data="server_reboot"
                ),
            ],
            [
                InlineKeyboardButton(text="⚙️ Службы", callback_data="server_services"),
                InlineKeyboardButton(
                    text="👥 Кто онлайн", callback_data="server_online"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚠️ Пороги нагрузки", callback_data="server_thresholds"
                ),
                InlineKeyboardButton(text="📈 Процессы", callback_data="server_htop"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"),
            ],
        ]
    )


def create_htop_keyboard(sort_by: str = "cpu"):
    sort_by = "mem" if sort_by == "mem" else "cpu"
    cpu_mark = "✅ " if sort_by == "cpu" else ""
    mem_mark = "✅ " if sort_by == "mem" else ""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{cpu_mark}CPU", callback_data="server_htop_cpu"
                ),
                InlineKeyboardButton(
                    text=f"{mem_mark}RAM", callback_data="server_htop_mem"
                ),
                InlineKeyboardButton(
                    text="🔄",
                    callback_data=f"server_htop_refresh_{sort_by}",
                ),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="server_menu")],
        ]
    )


def create_thresholds_menu():
    """Создать меню порогов нагрузки."""
    cpu_threshold, memory_threshold = get_load_thresholds()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"CPU: {cpu_threshold}%", callback_data="server_thresholds"
                ),
                InlineKeyboardButton(
                    text="Изменить CPU", callback_data="set_cpu_threshold"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"RAM: {memory_threshold}%", callback_data="server_thresholds"
                ),
                InlineKeyboardButton(
                    text="Изменить RAM", callback_data="set_memory_threshold"
                ),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="server_menu"),
            ],
        ]
    )


def create_reboot_confirm_menu():
    """Создать меню подтверждения перезагрузки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить перезагрузку",
                    callback_data="server_reboot_confirm",
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="server_menu")],
        ]
    )


def create_openvpn_menu():
    """Создать меню OpenVPN."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🆕 Создать клиента", callback_data="1"),
                InlineKeyboardButton(text="❌ Удалить клиента", callback_data="2"),
            ],
            [
                InlineKeyboardButton(text="📝 Список клиентов", callback_data="3"),
                InlineKeyboardButton(
                    text="🔄 Продлить", callback_data="ovpn_renew"
                ),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"),
            ],
        ]
    )


def create_openvpn_renew_clients_keyboard(
    clients: list[str],
    page: int,
    total_pages: int,
    expiry_labels: dict[str, str],
):
    """Создать список OpenVPN-клиентов для продления сертификата."""
    buttons = []
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE

    for client_name in clients[start_idx:end_idx]:
        expiry = expiry_labels.get(client_name, "срок неизвестен")
        text = f"{client_name} · {expiry}"
        if len(text) > 64:
            text = text[:61] + "…"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"ovpn_renew_client_{client_name}",
                )
            ]
        )

    pagination = []
    if page > 1:
        pagination.append(
            InlineKeyboardButton(
                text="⬅️ Предыдущая",
                callback_data=f"ovpn_renew_page_{page - 1}",
            )
        )
    if page < total_pages:
        pagination.append(
            InlineKeyboardButton(
                text="Следующая ➡️",
                callback_data=f"ovpn_renew_page_{page + 1}",
            )
        )
    if pagination:
        buttons.append(pagination)

    buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="openvpn_menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_openvpn_renew_days_keyboard():
    """Готовые сроки продления по аналогии с веб-интерфейсом."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="30 дн.", callback_data="ovpn_renew_days_30"),
                InlineKeyboardButton(text="90 дн.", callback_data="ovpn_renew_days_90"),
                InlineKeyboardButton(text="180 дн.", callback_data="ovpn_renew_days_180"),
            ],
            [
                InlineKeyboardButton(text="1 год", callback_data="ovpn_renew_days_365"),
                InlineKeyboardButton(text="10 лет", callback_data="ovpn_renew_days_3650"),
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Другой срок",
                    callback_data="ovpn_renew_days_custom",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К списку клиентов",
                    callback_data="ovpn_renew",
                )
            ],
        ]
    )


def create_openvpn_create_days_keyboard():
    """Готовые сроки для создания OpenVPN-клиента."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="30 дн.", callback_data="ovpn_create_days_30"),
                InlineKeyboardButton(text="90 дн.", callback_data="ovpn_create_days_90"),
                InlineKeyboardButton(text="180 дн.", callback_data="ovpn_create_days_180"),
            ],
            [
                InlineKeyboardButton(text="1 год", callback_data="ovpn_create_days_365"),
                InlineKeyboardButton(text="10 лет", callback_data="ovpn_create_days_3650"),
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Другой срок", callback_data="ovpn_create_days_custom"
                )
            ],
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data="ovpn_create_cancel")
            ],
        ]
    )


def create_wireguard_menu():
    """Создать меню WireGuard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🆕 Создать клиента", callback_data="4"),
                InlineKeyboardButton(text="❌ Удалить клиента", callback_data="5"),
            ],
            [
                InlineKeyboardButton(text="📝 Список клиентов", callback_data="6"),
                InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"),
            ],
        ]
    )


def _subscription_row(
    client_name: str,
    available: bool = True,
    telegram_id: int = None,
):
    if not available or not client_name:
        return None
    try:
        from src.ui.services.ovpn_subscription_service import (
            are_subscriptions_active,
            create_subscription_url,
            get_client_subscription_enabled,
        )
    except Exception:
        return None
    try:
        if (
            not are_subscriptions_active()
            or not get_client_subscription_enabled(client_name)
        ):
            return None
        url = create_subscription_url(client_name, telegram_id=telegram_id)
    except Exception:
        return None
    if not url:
        return None
    return [
        InlineKeyboardButton(
            text="🔗 Публичная ссылка",
            url=url,
        )
    ]


def create_openvpn_config_menu(
    client_name: str,
    back_callback: str = "back_to_client_list",
    telegram_id: int = None,
):
    """Создать меню выбора типа конфигурации OpenVPN."""
    from .config import get_effective_client_protocols

    buttons = []
    openvpn_available = True

    protocols = get_effective_client_protocols(client_name, telegram_id)
    openvpn_available = protocols.get("openvpn_vpn", True) or protocols.get(
        "openvpn_antizapret", True
    )
    openvpn_available = openvpn_available and any(
        protocols.get(key, True)
        for key in ("openvpn_default", "openvpn_tcp", "openvpn_udp")
    )

    if openvpn_available and protocols.get("openvpn_vpn", True):
        buttons.append(
            InlineKeyboardButton(
                text="VPN", callback_data=f"openvpn_config_vpn_{client_name}"
            )
        )
    if openvpn_available and protocols.get("openvpn_antizapret", True):
        buttons.append(
            InlineKeyboardButton(
                text="Antizapret",
                callback_data=f"openvpn_config_antizapret_{client_name}",
            )
        )
    rows = []
    if buttons:
        rows.append(buttons)
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="❌ Нет доступных конфигураций", callback_data="no_protocols"
                )
            ]
        )
        openvpn_available = False
    sub_row = _subscription_row(client_name, openvpn_available, telegram_id)
    if sub_row:
        rows.append(sub_row)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_openvpn_protocol_menu(interface: str, client_name: str):
    """Создать меню выбора протокола OpenVPN."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Стандартный (auto)",
                    callback_data=f"send_ovpn_{interface}_default_{client_name}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="TCP", callback_data=f"send_ovpn_{interface}_tcp_{client_name}"
                ),
                InlineKeyboardButton(
                    text="UDP", callback_data=f"send_ovpn_{interface}_udp_{client_name}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"back_to_interface_{interface}_{client_name}",
                ),
            ],
        ]
    )


def create_openvpn_protocol_menu_filtered(
    interface: str, client_name: str, protocols: dict
):
    """Создать меню выбора протокола OpenVPN с учётом ограничений клиента."""
    rows = []
    if protocols.get("openvpn_default", True):
        rows.append(
            [
                InlineKeyboardButton(
                    text="Стандартный (auto)",
                    callback_data=f"send_ovpn_{interface}_default_{client_name}",
                )
            ]
        )
    proto_row = []
    if protocols.get("openvpn_tcp", True):
        proto_row.append(
            InlineKeyboardButton(
                text="TCP", callback_data=f"send_ovpn_{interface}_tcp_{client_name}"
            )
        )
    if protocols.get("openvpn_udp", True):
        proto_row.append(
            InlineKeyboardButton(
                text="UDP", callback_data=f"send_ovpn_{interface}_udp_{client_name}"
            )
        )
    if proto_row:
        rows.append(proto_row)
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"back_to_interface_{interface}_{client_name}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_wireguard_config_menu(
    client_name: str,
    back_callback: str = "back_to_client_list",
    telegram_id: int = None,
):
    """Создать меню выбора типа конфигурации WireGuard."""
    from .config import get_effective_client_protocols

    buttons = []
    wireguard_available = True

    protocols = get_effective_client_protocols(client_name, telegram_id)
    wireguard_available = protocols.get("wireguard_vpn", True) or protocols.get(
        "wireguard_antizapret", True
    )
    wireguard_available = wireguard_available and any(
        protocols.get(key, True) for key in ("wireguard_wg", "wireguard_am")
    )

    if wireguard_available and protocols.get("wireguard_vpn", True):
        buttons.append(
            InlineKeyboardButton(
                text="VPN", callback_data=f"wireguard_config_vpn_{client_name}"
            )
        )
    if wireguard_available and protocols.get("wireguard_antizapret", True):
        buttons.append(
            InlineKeyboardButton(
                text="Antizapret",
                callback_data=f"wireguard_config_antizapret_{client_name}",
            )
        )
    rows = []
    if buttons:
        rows.append(buttons)
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="❌ Нет доступных конфигураций", callback_data="no_protocols"
                )
            ]
        )
        wireguard_available = False
    sub_row = _subscription_row(client_name, wireguard_available, telegram_id)
    if sub_row:
        rows.append(sub_row)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_wireguard_type_menu(interface: str, client_name: str):
    """Создать меню выбора типа WireGuard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="WireGuard",
                    callback_data=f"send_wg_{interface}_wg_{client_name}",
                ),
                InlineKeyboardButton(
                    text="AmneziaWG",
                    callback_data=f"send_wg_{interface}_am_{client_name}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад", callback_data=f"back_to_interface_{client_name}"
                )
            ],
        ]
    )


def create_wireguard_type_menu_filtered(
    interface: str, client_name: str, protocols: dict
):
    """Создать меню выбора типа WireGuard с учётом ограничений клиента."""
    type_buttons = []
    if protocols.get("wireguard_wg", True):
        type_buttons.append(
            InlineKeyboardButton(
                text="WireGuard",
                callback_data=f"send_wg_{interface}_wg_{client_name}",
            )
        )
    if protocols.get("wireguard_am", True):
        type_buttons.append(
            InlineKeyboardButton(
                text="AmneziaWG",
                callback_data=f"send_wg_{interface}_am_{client_name}",
            )
        )
    if not type_buttons:
        type_buttons.append(
            InlineKeyboardButton(
                text="❌ Нет доступных типов", callback_data="no_protocols"
            )
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            type_buttons,
            [
                InlineKeyboardButton(
                    text="⬅️ Назад", callback_data=f"back_to_interface_{client_name}"
                )
            ],
        ]
    )


def create_client_menu(client_name: str, telegram_id: int = None):
    """Создать меню выбора протокола для клиента."""
    from src.ui.services.ovpn_subscription_service import public_profile_items

    buttons = []
    items = public_profile_items(client_name, telegram_id)
    available_families = {item.get("family") for item in items}
    openvpn_available = "openvpn" in available_families
    wireguard_available = "wireguard" in available_families

    if openvpn_available:
        buttons.append(
            InlineKeyboardButton(
                text="OpenVPN", callback_data=f"client_openvpn_{client_name}"
            )
        )
    if wireguard_available:
        buttons.append(
            InlineKeyboardButton(
                text="WireGuard", callback_data=f"client_wireguard_{client_name}"
            )
        )
    rows = []
    if buttons:
        rows.append(buttons)
    sub_row = _subscription_row(
        client_name,
        openvpn_available or wireguard_available,
        telegram_id,
    )
    if sub_row:
        rows.append(sub_row)
    if not rows:
        rows = [
            [
                InlineKeyboardButton(
                    text="❌ Нет доступных протоколов", callback_data="no_protocols"
                )
            ]
        ]

    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_client_select_menu(client_names: list[str]):
    """Создать меню выбора клиента для пользователя с несколькими привязками."""
    rows = []
    max_name_len = 64 - len("pick_client_")
    for client_name in sorted(client_names, key=lambda name: name.lower()):
        safe_name = (client_name or "").strip()[:max_name_len]
        if not safe_name:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=safe_name,
                    callback_data=f"pick_client_{safe_name}",
                )
            ]
        )
    if not rows:
        rows.append(
            [
                InlineKeyboardButton(
                    text="❌ Нет доступных клиентов",
                    callback_data="no_action",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_notifications_menu(user_id: int):
    """Создать меню настроек уведомлений."""
    enabled = is_admin_notification_enabled(user_id)
    load_enabled = is_admin_load_notification_enabled(user_id)
    request_enabled = is_admin_request_notification_enabled(user_id)
    vpn_svc_enabled = is_admin_vpn_service_notification_enabled(user_id)
    status_text = "вкл ✅" if enabled else "выкл ❌"
    load_status = "вкл ✅" if load_enabled else "выкл ❌"
    request_status = "вкл ✅" if request_enabled else "выкл ❌"
    vpn_svc_status = "вкл ✅" if vpn_svc_enabled else "выкл ❌"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🔔 Уведомления: {status_text}",
                    callback_data="toggle_notifications",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"⚠️ Нагрузка: {load_status}",
                    callback_data="toggle_load_notifications",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"📩 Запрос доступа: {request_status}",
                    callback_data="toggle_request_notifications",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🔌 VPN-службы: {vpn_svc_status}",
                    callback_data="toggle_vpn_service_notifications",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")],
        ]
    )


def create_vpn_service_autorestart_cancel_keyboard(service_index: int):
    """Кнопки немедленного перезапуска и отмены таймера (callback_data ≤ 64 байт)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Перезапустить сейчас",
                    callback_data=f"vpn_ar_now_{service_index}",
                ),
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"vpn_ar_cancel_{service_index}",
                ),
            ],
        ]
    )


def create_server_services_keyboard():
    """Клавиатура экрана «Службы»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚙️ Выбор служб для мониторинга",
                    callback_data="server_services_monitor",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="server_menu")],
        ]
    )


def create_services_status_keyboard(vpn_services: list[tuple[str, str]]):
    """Клавиатура для управления мониторингом VPN-служб."""
    global_on = is_vpn_monitoring_enabled()
    global_mark = "вкл ✅" if global_on else "выкл ❌"
    rows = [
        [
            InlineKeyboardButton(
                text=f"🔌 Мониторинг VPN: {global_mark}",
                callback_data="toggle_vpn_monitoring_global",
            )
        ]
    ]
    for idx, (label, unit) in enumerate(vpn_services):
        enabled = is_vpn_service_monitored(unit)
        mark = "✅" if enabled else "❌"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {label}",
                    callback_data=f"toggle_vpn_monitor_{idx}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="server_services")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_pending_request_admin_text(
    telegram_id: str, fallback_suggested: str | None = None
) -> tuple[str, str]:
    uid = str(telegram_id).strip()
    entry = get_pending_access_requests().get(uid, {})
    display = "—"
    username_part = ""
    suggested = fallback_suggested or f"user_{uid}"
    if isinstance(entry, dict):
        display = (entry.get("display_name") or "").strip() or "—"
        username = (entry.get("username") or "").strip()
        if username:
            username_part = f" @{username}"
        suggested = (entry.get("suggested_name") or suggested).strip() or suggested
    text = (
        f"Клиент: {display}{username_part}\n"
        f"ID: <code>{uid}</code>\n\n"
        "Выберите клиента, введите имя клиента или отклоните запрос."
    )
    return text, suggested


def get_clients_menu_text(total_users: int, page: int = 1, total_bindings: int = 0) -> str:
    pending_count = get_pending_requests_count()
    base = (
        "Привязки клиентов:\n\n"
        "Чтобы удалить/настроить клиента — выберите пользователя, затем нужного клиента.\n"
        "Раздел «Запросы» — ожидающие подтверждения заявки на доступ.\n"
        "Раздел «Заблокированные» — пользователи, которым бот не отвечает."
    )
    if pending_count:
        base += f"\n\nОжидают обработки: <b>{pending_count}</b>."
    if total_bindings:
        base += f"\n\nПользователей: <b>{total_users}</b>, привязок: <b>{total_bindings}</b>."
    if total_users <= ITEMS_PER_PAGE:
        return base
    total_pages = max(1, (total_users + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(1, min(page, total_pages))
    return f"{base}\n\nСтраница {page} из {total_pages}."


def _sorted_client_mapping_items():
    return get_client_mapping_entries()


def clients_menu_page_for_telegram_id(telegram_id: str, client_name: str = "") -> int:
    """Номер страницы списка пользователей, на которой находится telegram_id."""
    sorted_user_ids = sorted(get_client_mapping().keys())
    for idx, tid in enumerate(sorted_user_ids):
        if tid == telegram_id:
            return idx // ITEMS_PER_PAGE + 1
    return 1


def create_clients_menu(admin_ids: list, page: int = 1):
    """Создать меню привязок клиентов: одна строка на пользователя."""
    mapping = get_client_mapping()
    sorted_user_ids = sorted(mapping.keys())
    users_total = len(sorted_user_ids)
    total_bindings = sum(len(names) for names in mapping.values())
    total_pages = (
        max(1, (users_total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE) if users_total else 1
    )
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * ITEMS_PER_PAGE
    chunk_user_ids = sorted_user_ids[start_idx : start_idx + ITEMS_PER_PAGE]

    buttons = [
        [
            InlineKeyboardButton(
                text="➕ Добавить привязку", callback_data="clientmap_add"
            )
        ]
    ]

    if chunk_user_ids:
        for display_idx, telegram_id in enumerate(chunk_user_ids, start=start_idx + 1):
            client_names = mapping.get(telegram_id, [])
            client_count = len(client_names)
            if client_count == 1:
                suffix = client_names[0]
            else:
                suffix = f"Клиентов: {client_count} шт."
            label = f"{display_idx}. {get_user_label(telegram_id)} ({suffix})"
            if len(label) > 64:
                label = label[:61] + "…"
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=f"clientmap_user_{telegram_id}",
                    )
                ]
            )
    elif not sorted_user_ids:
        buttons.append(
            [InlineKeyboardButton(text="📭 Пользователей нет", callback_data="no_action")]
        )

    nav = []
    if page > 1:
        nav.append(
            InlineKeyboardButton(text="⬅️ Предыдущая", callback_data=f"clients_p_{page - 1}")
        )
    if page < total_pages:
        nav.append(
            InlineKeyboardButton(text="Следующая ➡️", callback_data=f"clients_p_{page + 1}")
        )
    if nav:
        buttons.append(nav)

    pending_count = get_pending_requests_count()
    requests_label = (
        f"📩 Запросы ({pending_count})" if pending_count else "📩 Запросы"
    )
    buttons.append(
        [
            InlineKeyboardButton(
                text=requests_label, callback_data="pending_requests_menu"
            ),
            InlineKeyboardButton(
                text="📣 Рассылка", callback_data="broadcast_start"
            ),
        ]
    )
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_broadcast_input_keyboard():
    """Клавиатура ввода сообщения для рассылки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отмена", callback_data="broadcast_cancel"
                )
            ]
        ]
    )


def create_broadcast_confirmation_keyboard(config_warning: bool = False):
    """Клавиатура подтверждения рассылки."""
    confirm_text = "⚠️ Всё равно отправить" if config_warning else "✅ Отправить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=confirm_text, callback_data="broadcast_confirm"
                ),
                InlineKeyboardButton(
                    text="❌ Отмена", callback_data="broadcast_cancel"
                ),
            ]
        ]
    )


def create_client_user_menu(telegram_id: str, client_names: list[str], page: int = 1):
    """Создать меню клиентов конкретного Telegram-пользователя."""
    unique_names = []
    for name in client_names:
        clean_name = (name or "").strip()
        if clean_name and clean_name not in unique_names:
            unique_names.append(clean_name)
    unique_names.sort(key=lambda x: x.lower())

    total = len(unique_names)
    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE) if total else 1
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * ITEMS_PER_PAGE
    chunk = unique_names[start_idx : start_idx + ITEMS_PER_PAGE]

    buttons = [
        [
            InlineKeyboardButton(
                text="➕ Добавить к пользователю",
                callback_data=f"clientmap_add_for_{telegram_id}",
            )
        ]
    ]
    max_name_len = 64 - len(f"clientmap_{telegram_id}_")
    for idx, client_name in enumerate(chunk, start=start_idx + 1):
        safe_name = client_name[:max_name_len]
        label = f"{idx}. {client_name}"
        if len(label) > 64:
            label = label[:61] + "…"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"clientmap_{telegram_id}_{safe_name}",
                )
            ]
        )

    if not chunk:
        buttons.append(
            [InlineKeyboardButton(text="📭 Привязок нет", callback_data="no_action")]
        )

    nav = []
    if page > 1:
        nav.append(
            InlineKeyboardButton(
                text="⬅️ Предыдущая",
                callback_data=f"clientuser_p_{telegram_id}_{page - 1}",
            )
        )
    if page < total_pages:
        nav.append(
            InlineKeyboardButton(
                text="Следующая ➡️",
                callback_data=f"clientuser_p_{telegram_id}_{page + 1}",
            )
        )
    if nav:
        buttons.append(nav)

    return_page = clients_menu_page_for_telegram_id(telegram_id)
    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ К списку пользователей",
                callback_data=f"clients_p_{return_page}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _build_client_owners_map(client_mapping: dict[str, list[str]]) -> dict[str, list[str]]:
    owners = {}
    for telegram_id, names in client_mapping.items():
        for name in names:
            clean_name = (name or "").strip()
            if not clean_name:
                continue
            owners.setdefault(clean_name, [])
            if telegram_id not in owners[clean_name]:
                owners[clean_name].append(telegram_id)
    return owners


def create_clientmap_users_menu(page: int = 1):
    """Список пользователей для выбора при добавлении привязки."""
    mapping = get_client_mapping()
    pending_ids = set(get_pending_access_requests().keys())
    user_ids = get_clientmap_selectable_user_ids()
    total = len(user_ids)
    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE) if total else 1
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * ITEMS_PER_PAGE
    chunk = user_ids[start_idx : start_idx + ITEMS_PER_PAGE]

    buttons = [
        [InlineKeyboardButton(text="✏️ Ввести вручную", callback_data="clientmap_add_manual")]
    ]
    for user_id in chunk:
        count = len(mapping.get(user_id, []))
        if user_id in pending_ids and count:
            suffix = f"Клиентов: {count} шт., запрос"
        elif user_id in pending_ids:
            suffix = "запрос доступа"
        elif count == 1:
            suffix = mapping[user_id][0]
        elif count:
            suffix = f"Клиентов: {count} шт."
        else:
            suffix = "—"
        label = f"{get_user_label(user_id)} ({suffix})"
        if len(label) > 64:
            label = label[:61] + "…"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"clientmap_add_for_{user_id}",
                )
            ]
        )

    if not chunk:
        buttons.append([InlineKeyboardButton(text="Пользователей пока нет", callback_data="no_action")])

    nav = []
    if page > 1:
        nav.append(
            InlineKeyboardButton(
                text="⬅️ Предыдущая",
                callback_data=f"clientmap_users_p_{page - 1}",
            )
        )
    if page < total_pages:
        nav.append(
            InlineKeyboardButton(
                text="Следующая ➡️",
                callback_data=f"clientmap_users_p_{page + 1}",
            )
        )
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="clients_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_clientmap_client_list_menu(
    telegram_id: str,
    clients: list[str],
    page: int,
    total_pages: int,
):
    """Список VPN-клиентов для привязки к выбранному пользователю."""
    mapping = get_client_mapping()
    user_clients = set(mapping.get(str(telegram_id), []))
    owners_map = _build_client_owners_map(mapping)
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_clients = clients[start_idx:end_idx]

    max_name_len = 64 - len(f"clientmap_bind_{telegram_id}_")
    buttons = []
    for name in page_clients:
        safe_name = (name or "").strip()[:max_name_len]
        if not safe_name:
            continue
        owners = owners_map.get(name, [])
        if name in user_clients:
            status = "🟡 уже привязан"
        elif owners:
            if len(owners) == 1:
                status = f"{get_user_label(owners[0])}"
            else:
                status = f"Клиентов: {len(owners)} шт."
        else:
            status = "✅ свободен"
        text = f"{name} → {status}"
        if len(text) > 64:
            text = text[:61] + "…"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"clientmap_bind_{telegram_id}_{safe_name}",
                )
            ]
        )

    if not buttons:
        buttons.append([InlineKeyboardButton(text="📭 Нет клиентов", callback_data="no_action")])

    nav = []
    if page > 1:
        nav.append(
            InlineKeyboardButton(
                text="⬅️ Предыдущая",
                callback_data=f"clientmap_clients_p_{telegram_id}_{page - 1}",
            )
        )
    if page < total_pages:
        nav.append(
            InlineKeyboardButton(
                text="Следующая ➡️",
                callback_data=f"clientmap_clients_p_{telegram_id}_{page + 1}",
            )
        )
    if nav:
        buttons.append(nav)

    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ К выбору пользователя",
                callback_data="clientmap_add",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_pending_requests_menu_text(count: int, page: int = 1) -> str:
    base = (
        "📩 <b>Запросы доступа</b>\n\n"
        "Пользователи, ожидающие подтверждения. Выберите строку для обработки."
    )
    if not count:
        return f"{base}\n\nСейчас запросов нет."
    total_pages = max(1, (count + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(1, min(page, total_pages))
    if count <= ITEMS_PER_PAGE:
        return f"{base}\n\nВ очереди: <b>{count}</b>."
    return f"{base}\n\nВ очереди: <b>{count}</b>. Страница {page} из {total_pages}."


def create_pending_requests_menu(page: int = 1):
    user_ids = get_pending_request_user_ids()
    pending = get_pending_access_requests()
    total = len(user_ids)
    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE) if total else 1
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * ITEMS_PER_PAGE
    chunk = user_ids[start_idx : start_idx + ITEMS_PER_PAGE]

    buttons = []
    for uid in chunk:
        entry = pending.get(uid, {})
        display = "—"
        if isinstance(entry, dict):
            display = (entry.get("display_name") or "").strip() or "—"
        label = f"{get_user_label(uid)} — {display}"
        if len(label) > 64:
            label = label[:61] + "…"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"pending_req_{uid}",
                )
            ]
        )

    if not chunk:
        buttons.append(
            [InlineKeyboardButton(text="— список пуст —", callback_data="pending_noop")]
        )

    nav = []
    if page > 1:
        nav.append(
            InlineKeyboardButton(
                text="⬅️ Предыдущая", callback_data=f"pending_p_{page - 1}"
            )
        )
    if page < total_pages:
        nav.append(
            InlineKeyboardButton(
                text="Следующая ➡️", callback_data=f"pending_p_{page + 1}"
            )
        )
    if nav:
        buttons.append(nav)

    buttons.append(
        [
            InlineKeyboardButton(
                text="🚫 Заблокированные", callback_data="banned_menu"
            )
        ]
    )
    buttons.append(
        [InlineKeyboardButton(text="⬅️ К клиентам бота", callback_data="clients_menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_banned_list_keyboard(sorted_ids: list, page: int):
    """Постраничный список заблокированных user id с кнопкой разблокировки по строке."""
    buttons = []
    total = len(sorted_ids)
    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE) if total else 1
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * ITEMS_PER_PAGE
    chunk = sorted_ids[start_idx : start_idx + ITEMS_PER_PAGE]

    for uid in chunk:
        uid_str = str(uid)
        label = get_user_label(uid_str)
        btn_text = f"✅ Разблокировать {label}"
        if len(btn_text) > 64:
            btn_text = btn_text[:61] + "…"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"ban_rm_{uid_str}_{page}",
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton(text="➕ Заблокировать по ID", callback_data="ban_add")]
    )
    if not chunk and not sorted_ids:
        buttons.append(
            [InlineKeyboardButton(text="— список пуст —", callback_data="banned_noop")]
        )

    nav = []
    if page > 1:
        nav.append(
            InlineKeyboardButton(text="⬅️ Предыдущая", callback_data=f"banned_p_{page - 1}")
        )
    if page < total_pages:
        nav.append(
            InlineKeyboardButton(text="Следующая ➡️", callback_data=f"banned_p_{page + 1}")
        )
    if nav:
        buttons.append(nav)

    buttons.append(
        [InlineKeyboardButton(text="⬅️ К запросам", callback_data="pending_requests_menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_admins_menu(admin_ids: list):
    """Создать меню списка администраторов."""
    buttons = []

    if admin_ids:
        for admin_id in admin_ids:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=get_user_label(str(admin_id)),
                        callback_data="no_action",
                    )
                ]
            )
    else:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="Администраторы не настроены", callback_data="no_action"
                )
            ]
        )

    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_clientmap_delete_menu(telegram_id: str, client_name: str):
    """Создать меню подтверждения удаления привязки клиента."""
    max_name_len = 64 - len(f"clientmap_delete_confirm_{telegram_id}_")
    safe_name = (client_name or "")[:max_name_len]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Удалить",
                    callback_data=f"clientmap_delete_confirm_{telegram_id}_{safe_name}",
                ),
                InlineKeyboardButton(text="❌ Отмена", callback_data="clients_menu"),
            ]
        ]
    )


def _status_badge(status: dict | None) -> str:
    state = (status or {}).get("state")
    if state == "online":
        return "🟢"
    if state == "blocked":
        return "🔴🚫"
    return "🔴"


def create_client_list_keyboard(
    clients,
    page,
    total_pages,
    vpn_type,
    action,
    statuses: dict | None = None,
):
    """Создать постраничную клавиатуру со списком клиентов."""
    buttons = []
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE

    for client in clients[start_idx:end_idx]:
        if action == "delete":
            callback_data = f"delete_{vpn_type}_{client}"
            text = client
        else:
            callback_data = f"clist_{vpn_type}_{page}_{client}"
            text = f"{_status_badge((statuses or {}).get(client))} {client}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

    pagination = []
    if page > 1:
        pagination.append(
            InlineKeyboardButton(
                text="⬅️ Предыдущая", callback_data=f"page_{action}_{vpn_type}_{page-1}"
            )
        )
    if page < total_pages:
        pagination.append(
            InlineKeyboardButton(
                text="Следующая ➡️", callback_data=f"page_{action}_{vpn_type}_{page+1}"
            )
        )

    if pagination:
        buttons.append(pagination)

    buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{vpn_type}_menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_client_actions_keyboard(
    vpn_type: str,
    client_name: str,
    is_blocked: bool,
    list_page: int,
):
    block_text = "✅ Разблокировать" if is_blocked else "🚫 Заблокировать"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=block_text,
                    callback_data=f"ctg_{vpn_type}_{list_page}_{client_name}",
                ),
                InlineKeyboardButton(
                    text="📁 Конфиг файлы",
                    callback_data=f"ccfg_{vpn_type}_{list_page}_{client_name}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К списку",
                    callback_data=f"page_list_{vpn_type}_{list_page}",
                )
            ],
        ]
    )


def create_confirmation_keyboard(client_name, vpn_type):
    """Создать клавиатуру подтверждения удаления."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"confirm_{vpn_type}_{client_name}",
                ),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete"),
            ]
        ]
    )


def create_back_keyboard(callback_data: str):
    """Создать клавиатуру с кнопкой «Назад»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data)]
        ]
    )


def create_rename_confirmation_keyboard():
    """Создать клавиатуру подтверждения переименования файлов WireGuard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data="confirm_rename"),
                InlineKeyboardButton(text="❌ Нет", callback_data="no_rename"),
            ]
        ]
    )


def create_settings_import_keyboard():
    """Создать клавиатуру подтверждения замены settings.json."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Заменить",
                    callback_data="settings_import_confirm",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="settings_import_cancel",
                ),
            ]
        ]
    )


def create_request_access_keyboard():
    """Создать клавиатуру для неавторизованного пользователя (запросить доступ)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📩 Запросить доступ",
                    callback_data="request_access",
                ),
            ],
        ]
    )


def create_request_actions_keyboard(requester_user_id: int, suggested_name: str = None):
    """Клавиатура запроса доступа: Выбрать клиента, Ввести имя, Отклонить или Заблокировать.
    suggested_name используется для callback req_pick/req_back (список и «Назад»).
    """
    uid = str(requester_user_id)
    safe_name = (suggested_name or f"user_{uid}")[: (64 - len(f"req_pick_{uid}_"))]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Выбрать",
                    callback_data=f"req_pick_{uid}_{safe_name}",
                ),
                InlineKeyboardButton(
                    text="✏️ Ввести имя",
                    callback_data=f"req_custom_{uid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"req_no_{uid}",
                ),
                InlineKeyboardButton(
                    text="🚫 Заблокировать",
                    callback_data=f"req_ban_{uid}",
                ),
            ],
        ]
    )


def create_request_client_list_keyboard(
    requester_uid: str,
    clients: list,
    page: int,
    total_pages: int,
    suggested_name: str,
):
    """Клавиатура выбора существующего клиента для привязки к запросу доступа."""
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_clients = clients[start_idx:end_idx]
    # callback_data до 64 байт: req_bind_ = 8, uid до 11, _ = 1 → остаётся до 44 символов для имени
    max_name_len = 64 - len(f"req_bind_{requester_uid}_")
    buttons = []
    for name in page_clients:
        safe_name = (name or "")[:max_name_len]
        if not safe_name:
            continue
        buttons.append(
            [
                InlineKeyboardButton(
                    text=name,
                    callback_data=f"req_bind_{requester_uid}_{safe_name}",
                )
            ]
        )
    pagination = []
    if page > 1:
        pagination.append(
            InlineKeyboardButton(
                text="⬅️ Предыдущая",
                callback_data=f"req_list_{requester_uid}_{page - 1}",
            )
        )
    if page < total_pages:
        pagination.append(
            InlineKeyboardButton(
                text="Следующая ➡️",
                callback_data=f"req_list_{requester_uid}_{page + 1}",
            )
        )
    if pagination:
        buttons.append(pagination)
    back_suggested = (suggested_name or f"user_{requester_uid}")[
        : (64 - len(f"req_back_{requester_uid}_"))
    ]
    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад к запросу",
                callback_data=f"req_back_{requester_uid}_{back_suggested}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_client_protocols_menu(
    telegram_id: str,
    client_name: str = "",
    back_callback: str = "clients_menu",
):
    """Создать меню настройки доступных протоколов для клиента."""
    from src.ui.services.settings_service import (
        get_available_vpn_client_protocol_keys,
        get_vpn_client_protocols,
    )
    from .config import get_client_allowed_protocols

    protocols = get_vpn_client_protocols(client_name)
    available_keys = get_available_vpn_client_protocol_keys(client_name)
    telegram_protocols = get_client_allowed_protocols(telegram_id)

    def status(key):
        return "✅" if protocols.get(key, True) else "❌"

    button_specs = (
        (("openvpn_vpn", "OVPN VPN", "toggle_proto_ovpn_vpn_"),
         ("openvpn_antizapret", "OVPN Antizapret", "toggle_proto_ovpn_az_")),
        (("wireguard_vpn", "WG VPN", "toggle_proto_wg_vpn_"),
         ("wireguard_antizapret", "WG Antizapret", "toggle_proto_wg_az_")),
        (("openvpn_default", "OVPN Стандартный", "toggle_proto_ovpn_default_"),),
        (("openvpn_tcp", "OVPN TCP", "toggle_proto_ovpn_tcp_"),
         ("openvpn_udp", "OVPN UDP", "toggle_proto_ovpn_udp_")),
        (("wireguard_wg", "WireGuard", "toggle_proto_wg_type_wg_"),
         ("wireguard_am", "AmneziaWG", "toggle_proto_wg_type_am_")),
    )
    rows = []
    for specs in button_specs:
        row = [
            InlineKeyboardButton(
                text=f"{label}: {status(key)}",
                callback_data=f"{prefix}{telegram_id}",
            )
            for key, label, prefix in specs
            if key in available_keys
        ]
        if row:
            rows.append(row)
    if not rows:
        rows.append(
            [InlineKeyboardButton(text="❌ Конфиги не найдены", callback_data="no_action")]
        )
    if any(not telegram_protocols.get(key, True) for key in available_keys):
        rows.append([
            InlineKeyboardButton(
                text="⚠️ Есть дополнительные ограничения Telegram ID",
                callback_data="telegram_access_info",
            )
        ])
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🗑️ Удалить привязку",
                    callback_data=f"clientmap_delete_{telegram_id}_{client_name}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=back_callback,
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_client_protocols_transport_menu(
    telegram_id: str,
    client_name: str = "",
    back_callback: str = "clients_menu",
):
    """Совместимость со старым вызовом: используем общее меню."""
    return create_client_protocols_menu(telegram_id, client_name, back_callback)
