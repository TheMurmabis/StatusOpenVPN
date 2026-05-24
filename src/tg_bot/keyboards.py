"""Построители клавиатур для Telegram-бота."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import (
    ITEMS_PER_PAGE,
    get_client_mapping,
    get_load_thresholds,
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
                InlineKeyboardButton(text="📦 Создать бэкап", callback_data="8"),
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
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"),
            ],
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
                InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"),
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


def create_openvpn_config_menu(
    client_name: str,
    back_callback: str = "back_to_client_list",
    telegram_id: int = None,
):
    """Создать меню выбора типа конфигурации OpenVPN."""
    from .config import get_client_allowed_protocols

    buttons = []

    # Если telegram_id передан, проверяем доступные протоколы
    if telegram_id is not None:
        protocols = get_client_allowed_protocols(str(telegram_id))

        if protocols.get("openvpn_vpn", True):
            buttons.append(
                InlineKeyboardButton(
                    text="VPN", callback_data=f"openvpn_config_vpn_{client_name}"
                )
            )
        if protocols.get("openvpn_antizapret", True):
            buttons.append(
                InlineKeyboardButton(
                    text="Antizapret",
                    callback_data=f"openvpn_config_antizapret_{client_name}",
                )
            )
    else:
        # По умолчанию показываем оба варианта
        buttons = [
            InlineKeyboardButton(
                text="VPN", callback_data=f"openvpn_config_vpn_{client_name}"
            ),
            InlineKeyboardButton(
                text="Antizapret",
                callback_data=f"openvpn_config_antizapret_{client_name}",
            ),
        ]

    # Если нет доступных вариантов
    if not buttons:
        buttons = [
            InlineKeyboardButton(
                text="❌ Нет доступных конфигураций", callback_data="no_protocols"
            )
        ]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            buttons,
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
        ]
    )


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
    from .config import get_client_allowed_protocols

    buttons = []

    # Если telegram_id передан, проверяем доступные протоколы
    if telegram_id is not None:
        protocols = get_client_allowed_protocols(str(telegram_id))

        if protocols.get("wireguard_vpn", True):
            buttons.append(
                InlineKeyboardButton(
                    text="VPN", callback_data=f"wireguard_config_vpn_{client_name}"
                )
            )
        if protocols.get("wireguard_antizapret", True):
            buttons.append(
                InlineKeyboardButton(
                    text="Antizapret",
                    callback_data=f"wireguard_config_antizapret_{client_name}",
                )
            )
    else:
        # По умолчанию показываем оба варианта
        buttons = [
            InlineKeyboardButton(
                text="VPN", callback_data=f"wireguard_config_vpn_{client_name}"
            ),
            InlineKeyboardButton(
                text="Antizapret",
                callback_data=f"wireguard_config_antizapret_{client_name}",
            ),
        ]

    # Если нет доступных вариантов
    if not buttons:
        buttons = [
            InlineKeyboardButton(
                text="❌ Нет доступных конфигураций", callback_data="no_protocols"
            )
        ]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            buttons,
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
        ]
    )


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
    from .config import get_client_allowed_protocols

    buttons = []

    # Если telegram_id передан, проверяем доступные протоколы
    if telegram_id is not None:
        protocols = get_client_allowed_protocols(str(telegram_id))

        # Проверяем, доступен ли хотя бы один вариант OpenVPN
        openvpn_available = protocols.get("openvpn_vpn", True) or protocols.get(
            "openvpn_antizapret", True
        )
        # Проверяем, доступен ли хотя бы один вариант WireGuard
        wireguard_available = protocols.get("wireguard_vpn", True) or protocols.get(
            "wireguard_antizapret", True
        )

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
    else:
        # По умолчанию показываем оба протокола (для обратной совместимости)
        buttons = [
            InlineKeyboardButton(
                text="OpenVPN", callback_data=f"client_openvpn_{client_name}"
            ),
            InlineKeyboardButton(
                text="WireGuard", callback_data=f"client_wireguard_{client_name}"
            ),
        ]

    # Если нет доступных протоколов, показываем сообщение
    if not buttons:
        buttons = [
            InlineKeyboardButton(
                text="❌ Нет доступных протоколов", callback_data="no_protocols"
            )
        ]

    return InlineKeyboardMarkup(inline_keyboard=[buttons])


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


def get_clients_menu_text(total: int, page: int = 1) -> str:
    base = (
        "Привязки клиентов:\n\n"
        "Чтобы удалить/настроить клиента — нажмите на неё в списке.\n"
        "Раздел «Заблокированные» — пользователи, которым бот не отвечает."
    )
    if total <= ITEMS_PER_PAGE:
        return base
    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(1, min(page, total_pages))
    return f"{base}\n\nСтраница {page} из {total_pages}."


def _sorted_client_mapping_items():
    return sorted(get_client_mapping().items(), key=lambda x: x[0])


def clients_menu_page_for_telegram_id(telegram_id: str) -> int:
    """Номер страницы списка привязок, на которой находится клиент."""
    for idx, (tid, _) in enumerate(_sorted_client_mapping_items()):
        if tid == telegram_id:
            return idx // ITEMS_PER_PAGE + 1
    return 1


def create_clients_menu(admin_ids: list, page: int = 1):
    """Создать меню привязок клиентов (по ITEMS_PER_PAGE на страницу)."""
    sorted_items = _sorted_client_mapping_items()
    total = len(sorted_items)
    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE) if total else 1
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * ITEMS_PER_PAGE
    chunk = sorted_items[start_idx : start_idx + ITEMS_PER_PAGE]

    buttons = [
        [
            InlineKeyboardButton(
                text="➕ Добавить привязку", callback_data="clientmap_add"
            )
        ]
    ]

    if chunk:
        for display_idx, (telegram_id, client_name) in enumerate(
            chunk, start=start_idx + 1
        ):
            label = f"{display_idx}. {get_user_label(telegram_id)} → {client_name}"
            if len(label) > 64:
                label = label[:61] + "…"
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=f"clientmap_{telegram_id}",
                    )
                ]
            )
    elif not sorted_items:
        buttons.append(
            [InlineKeyboardButton(text="📭 Привязок нет", callback_data="no_action")]
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

    buttons.append(
        [
            InlineKeyboardButton(
                text="🚫 Заблокированные", callback_data="banned_menu"
            ),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"),
        ]
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
        [InlineKeyboardButton(text="⬅️ К клиентам бота", callback_data="clients_menu")]
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
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Удалить",
                    callback_data=f"clientmap_delete_confirm_{telegram_id}",
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


def create_client_protocols_menu(telegram_id: str):
    """Создать меню настройки доступных протоколов для клиента."""
    from .config import get_client_allowed_protocols

    protocols = get_client_allowed_protocols(telegram_id)
    ovpn_vpn_status = "✅" if protocols.get("openvpn_vpn", True) else "❌"
    ovpn_az_status = "✅" if protocols.get("openvpn_antizapret", True) else "❌"
    wg_vpn_status = "✅" if protocols.get("wireguard_vpn", True) else "❌"
    wg_az_status = "✅" if protocols.get("wireguard_antizapret", True) else "❌"
    ovpn_def_status = "✅" if protocols.get("openvpn_default", True) else "❌"
    ovpn_tcp_status = "✅" if protocols.get("openvpn_tcp", True) else "❌"
    ovpn_udp_status = "✅" if protocols.get("openvpn_udp", True) else "❌"
    wg_wg_status = "✅" if protocols.get("wireguard_wg", True) else "❌"
    wg_am_status = "✅" if protocols.get("wireguard_am", True) else "❌"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"OVPN VPN: {ovpn_vpn_status}",
                    callback_data=f"toggle_proto_ovpn_vpn_{telegram_id}",
                ),
                InlineKeyboardButton(
                    text=f"OVPN Antizapret: {ovpn_az_status}",
                    callback_data=f"toggle_proto_ovpn_az_{telegram_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"WG VPN: {wg_vpn_status}",
                    callback_data=f"toggle_proto_wg_vpn_{telegram_id}",
                ),
                InlineKeyboardButton(
                    text=f"WG Antizapret: {wg_az_status}",
                    callback_data=f"toggle_proto_wg_az_{telegram_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"OVPN Стандартный: {ovpn_def_status}",
                    callback_data=f"toggle_proto_ovpn_default_{telegram_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"OVPN TCP: {ovpn_tcp_status}",
                    callback_data=f"toggle_proto_ovpn_tcp_{telegram_id}",
                ),
                InlineKeyboardButton(
                    text=f"OVPN UDP: {ovpn_udp_status}",
                    callback_data=f"toggle_proto_ovpn_udp_{telegram_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"WireGuard: {wg_wg_status}",
                    callback_data=f"toggle_proto_wg_type_wg_{telegram_id}",
                ),
                InlineKeyboardButton(
                    text=f"AmneziaWG: {wg_am_status}",
                    callback_data=f"toggle_proto_wg_type_am_{telegram_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑️ Удалить привязку",
                    callback_data=f"clientmap_delete_{telegram_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="clients_menu",
                )
            ],
        ]
    )


def create_client_protocols_transport_menu(telegram_id: str):
    """Совместимость со старым вызовом: используем общее меню."""
    return create_client_protocols_menu(telegram_id)
