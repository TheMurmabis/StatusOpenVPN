"""Построители клавиатур для Telegram-бота."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import (
    ITEMS_PER_PAGE,
    get_client_mapping,
    get_load_thresholds,
)
from .admin import (
    is_admin_notification_enabled,
    is_admin_load_notification_enabled,
    is_admin_request_notification_enabled,
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
                InlineKeyboardButton(text="👥 Клиенты бота", callback_data="clients_menu"),
                InlineKeyboardButton(text="👤 Администраторы", callback_data="admins_menu"),
            ],
            [
                InlineKeyboardButton(text="🔔 Уведомления", callback_data="notifications_menu"),
            ],
        ]
    )


def create_server_menu():
    """Создать меню управления сервером."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data="server_stats"),
                InlineKeyboardButton(text="🔄 Перезагрузка", callback_data="server_reboot"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Службы", callback_data="server_services"),
                InlineKeyboardButton(text="👥 Кто онлайн", callback_data="server_online"),
            ],
            [
                InlineKeyboardButton(text="⚠️ Пороги нагрузки", callback_data="server_thresholds"),
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
                InlineKeyboardButton(text=f"CPU: {cpu_threshold}%", callback_data="server_thresholds"),
                InlineKeyboardButton(text="Изменить CPU", callback_data="set_cpu_threshold"),
            ],
            [
                InlineKeyboardButton(text=f"RAM: {memory_threshold}%", callback_data="server_thresholds"),
                InlineKeyboardButton(text="Изменить RAM", callback_data="set_memory_threshold"),
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
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data="server_menu")
            ],
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


def create_openvpn_config_menu(client_name: str, back_callback: str = "back_to_client_list"):
    """Создать меню выбора типа конфигурации OpenVPN."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="VPN", callback_data=f"openvpn_config_vpn_{client_name}"),
                InlineKeyboardButton(text="Antizapret", callback_data=f"openvpn_config_antizapret_{client_name}"),
            ],
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
                InlineKeyboardButton(text="TCP", callback_data=f"send_ovpn_{interface}_tcp_{client_name}"),
                InlineKeyboardButton(text="UDP", callback_data=f"send_ovpn_{interface}_udp_{client_name}"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_interface_{interface}_{client_name}"),
            ],
        ]
    )


def create_wireguard_config_menu(client_name: str, back_callback: str = "back_to_client_list"):
    """Создать меню выбора типа конфигурации WireGuard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="VPN", callback_data=f"wireguard_config_vpn_{client_name}"),
                InlineKeyboardButton(text="Antizapret", callback_data=f"wireguard_config_antizapret_{client_name}"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
        ]
    )


def create_wireguard_type_menu(interface: str, client_name: str):
    """Создать меню выбора типа WireGuard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="WireGuard", callback_data=f"send_wg_{interface}_wg_{client_name}"),
                InlineKeyboardButton(text="AmneziaWG", callback_data=f"send_wg_{interface}_am_{client_name}"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_interface_{client_name}")
            ],
        ]
    )


def create_client_menu(client_name: str):
    """Создать меню выбора протокола для клиента."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="OpenVPN", callback_data=f"client_openvpn_{client_name}"),
                InlineKeyboardButton(text="WireGuard", callback_data=f"client_wireguard_{client_name}"),
            ],
        ]
    )


def create_notifications_menu(user_id: int):
    """Создать меню настроек уведомлений."""
    enabled = is_admin_notification_enabled(user_id)
    load_enabled = is_admin_load_notification_enabled(user_id)
    request_enabled = is_admin_request_notification_enabled(user_id)
    status_text = "вкл ✅" if enabled else "выкл ❌"
    load_status = "вкл ✅" if load_enabled else "выкл ❌"
    request_status = "вкл ✅" if request_enabled else "выкл ❌"
    
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
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")],
        ]
    )


def create_clients_menu(admin_ids: list):
    """Создать меню привязок клиентов."""
    client_map = get_client_mapping()
    buttons = []
    
    if client_map:
        for telegram_id, client_name in client_map.items():
            label = f"{get_user_label(telegram_id)}:{client_name}"
            buttons.append([
                InlineKeyboardButton(text=label, callback_data=f"clientmap_{telegram_id}")
            ])
    else:
        buttons.append([
            InlineKeyboardButton(text="Привязок нет", callback_data="no_action")
        ])
    
    buttons.append([InlineKeyboardButton(text="➕ Добавить", callback_data="clientmap_add")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_admins_menu(admin_ids: list):
    """Создать меню списка администраторов."""
    buttons = []
    
    if admin_ids:
        for admin_id in admin_ids:
            buttons.append([
                InlineKeyboardButton(
                    text=get_user_label(str(admin_id)),
                    callback_data="no_action",
                )
            ])
    else:
        buttons.append([
            InlineKeyboardButton(text="Администраторы не настроены", callback_data="no_action")
        ])
    
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_clientmap_delete_menu(telegram_id: str, client_name: str):
    """Создать меню подтверждения удаления привязки клиента."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Удалить", callback_data=f"clientmap_delete_confirm_{telegram_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="clients_menu"),
            ]
        ]
    )


def create_client_list_keyboard(clients, page, total_pages, vpn_type, action):
    """Создать постраничную клавиатуру со списком клиентов."""
    buttons = []
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    
    for client in clients[start_idx:end_idx]:
        if action == "delete":
            callback_data = f"delete_{vpn_type}_{client}"
        else:
            callback_data = f"client_{vpn_type}_{client}"
        buttons.append([InlineKeyboardButton(text=client, callback_data=callback_data)])
    
    pagination = []
    if page > 1:
        pagination.append(
            InlineKeyboardButton(text="⬅️ Предыдущая", callback_data=f"page_{action}_{vpn_type}_{page-1}")
        )
    if page < total_pages:
        pagination.append(
            InlineKeyboardButton(text="Следующая ➡️", callback_data=f"page_{action}_{vpn_type}_{page+1}")
        )
    
    if pagination:
        buttons.append(pagination)
    
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{vpn_type}_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_confirmation_keyboard(client_name, vpn_type):
    """Создать клавиатуру подтверждения удаления."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{vpn_type}_{client_name}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete"),
            ]
        ]
    )


def create_back_keyboard(callback_data: str):
    """Создать клавиатуру с кнопкой «Назад»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data)]]
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
    """Клавиатура запроса доступа: Выбрать клиента, Ввести имя или Отклонить.
    suggested_name используется для callback req_pick/req_back (список и «Назад»).
    """
    uid = str(requester_user_id)
    safe_name = (suggested_name or f"user_{uid}")[:(64 - len(f"req_pick_{uid}_"))]
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
        buttons.append([
            InlineKeyboardButton(
                text=name,
                callback_data=f"req_bind_{requester_uid}_{safe_name}",
            )
        ])
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
    back_suggested = (suggested_name or f"user_{requester_uid}")[:(64 - len(f"req_back_{requester_uid}_"))]
    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Назад к запросу",
            callback_data=f"req_back_{requester_uid}_{back_suggested}",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
