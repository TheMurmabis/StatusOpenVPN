"""Обработчики навигации по меню."""

from typing import Optional, Tuple

from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from ..config import (
    ITEMS_PER_PAGE,
    get_admin_ids,
    get_client_mapping,
    get_client_mapping_entries,
    remove_client_mapping,
    get_banned_user_ids,
    ban_user,
    unban_user,
    is_user_banned,
    add_client_mapping,
    get_pending_request_user_ids,
    get_pending_requests_count,
)
from ..admin import (
    is_admin_notification_enabled,
    set_admin_notification,
    is_admin_load_notification_enabled,
    set_admin_load_notification,
    is_admin_request_notification_enabled,
    set_admin_request_notification,
    is_admin_vpn_service_notification_enabled,
    set_admin_vpn_service_notification,
    get_user_label,
)
from ..keyboards import (
    create_main_menu,
    create_vpn_services_menu,
    create_openvpn_menu,
    create_wireguard_menu,
    create_server_menu,
    create_clients_menu,
    get_clients_menu_text,
    create_banned_list_keyboard,
    create_admins_menu,
    create_notifications_menu,
    create_clientmap_delete_menu,
    create_client_user_menu,
    create_clientmap_users_menu,
    create_clientmap_client_list_menu,
    create_back_keyboard,
    create_pending_requests_menu,
    get_pending_requests_menu_text,
    create_request_actions_keyboard,
    format_pending_request_admin_text,
)
from ..states import VPNSetup
from ..utils import get_external_ip, get_all_clients_unique
from ..audit import log_action

router = Router()


def _get_server_ip():
    return get_external_ip()


@router.callback_query(
    lambda c: c.data in [
        "main_menu",
        "vpn_services_menu",
        "openvpn_menu",
        "wireguard_menu",
        "server_menu",
        "clients_menu",
        "admins_menu",
    ]
)
async def handle_main_menus(callback: types.CallbackQuery, state: FSMContext):
    """Обработка навигации по главному меню."""
    admin_ids = get_admin_ids()
    
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    
    if callback.data == "main_menu":
        server_ip = _get_server_ip()
        await callback.message.edit_text("Главное меню:", reply_markup=create_main_menu(server_ip))
    elif callback.data == "vpn_services_menu":
        await callback.message.edit_text(
            "Выберите VPN сервис:", reply_markup=create_vpn_services_menu()
        )
    elif callback.data == "openvpn_menu":
        await callback.message.edit_text("Меню OpenVPN:", reply_markup=create_openvpn_menu())
    elif callback.data == "server_menu":
        await callback.message.edit_text("Меню сервера:", reply_markup=create_server_menu())
    elif callback.data == "clients_menu":
        await state.clear()
        mapping = get_client_mapping()
        total_users = len(mapping)
        total_bindings = sum(len(names) for names in mapping.values())
        await callback.message.edit_text(
            get_clients_menu_text(total_users, 1, total_bindings),
            reply_markup=create_clients_menu(admin_ids, 1),
        )
    elif callback.data == "admins_menu":
        await callback.message.edit_text("Администраторы:", reply_markup=create_admins_menu(admin_ids))
    else:
        await callback.message.edit_text("Меню WireGuard:", reply_markup=create_wireguard_menu())
    
    await callback.answer()


@router.callback_query(
    lambda c: c.data.startswith("clients_p_") and c.data.removeprefix("clients_p_").isdigit()
)
async def handle_clients_list_nav(callback: types.CallbackQuery, state: FSMContext):
    """Пагинация списка привязок клиентов бота."""
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return

    await state.clear()
    page = int(callback.data.removeprefix("clients_p_"))
    mapping = get_client_mapping()
    total_users = len(mapping)
    total_bindings = sum(len(names) for names in mapping.values())
    total_pages = (
        max(1, (total_users + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE) if total_users else 1
    )
    page = max(1, min(page, total_pages))

    await callback.message.edit_text(
        get_clients_menu_text(total_users, page, total_bindings),
        reply_markup=create_clients_menu(admin_ids, page),
    )
    await callback.answer()


@router.callback_query(
    lambda c: c.data.startswith("clientuser_p_")
    and len(c.data.split("_", 3)) == 4
    and c.data.rsplit("_", 1)[1].isdigit()
)
async def handle_client_user_nav(callback: types.CallbackQuery, state: FSMContext):
    """Пагинация списка клиентов одного пользователя."""
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    await state.clear()
    payload = callback.data.removeprefix("clientuser_p_")
    if "_" not in payload:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    telegram_id, page_raw = payload.rsplit("_", 1)
    page = int(page_raw)
    client_names = get_client_mapping().get(telegram_id, [])
    if not client_names:
        mapping = get_client_mapping()
        total_users = len(mapping)
        total_bindings = sum(len(names) for names in mapping.values())
        await callback.message.edit_text(
            "Пользователь или привязки не найдены.\n\n"
            + get_clients_menu_text(total_users, 1, total_bindings),
            reply_markup=create_clients_menu(admin_ids, 1),
        )
        await callback.answer()
        return
    if len(client_names) == 1:
        client_name = client_names[0]
        from ..keyboards import create_client_protocols_menu, clients_menu_page_for_telegram_id

        return_page = clients_menu_page_for_telegram_id(telegram_id)
        await callback.message.edit_text(
            f"Настройка клиента <code>{get_user_label(telegram_id)}</code> → <b>{client_name}</b>\n\n"
            "Настройка протоколов:",
            reply_markup=create_client_protocols_menu(
                telegram_id,
                client_name,
                f"clients_p_{return_page}",
            ),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        f"Пользователь: <code>{get_user_label(telegram_id)}</code>\n"
        f"Привязок: <b>{len(client_names)}</b>\n\n"
        "Выберите клиента для настройки:",
        reply_markup=create_client_user_menu(telegram_id, client_names, page),
    )
    await callback.answer()


@router.callback_query(
    lambda c: c.data.startswith("clientmap_") or c.data.startswith("client_proto_menu_")
)
async def handle_clientmap_actions(callback: types.CallbackQuery, state: FSMContext):
    """Обработка действий с привязками клиентов."""
    admin_ids = get_admin_ids()
    
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    
    data = callback.data
    
    if data == "clientmap_add":
        await callback.message.edit_text(
            "Выберите пользователя для привязки клиента.\n"
            "Можно выбрать из списка или ввести ID вручную.",
            reply_markup=create_clientmap_users_menu(1),
        )
        await state.clear()
        await callback.answer()
        return

    if data.startswith("clientmap_users_p_"):
        page_raw = data.removeprefix("clientmap_users_p_")
        if not page_raw.isdigit():
            await callback.answer("Некорректные данные", show_alert=True)
            return
        page = int(page_raw)
        await callback.message.edit_text(
            "Выберите пользователя для привязки клиента.\n"
            "Можно выбрать из списка или ввести ID вручную.",
            reply_markup=create_clientmap_users_menu(page),
        )
        await callback.answer()
        return

    if data == "clientmap_add_manual":
        await callback.message.edit_text(
            "Введите Telegram ID пользователя (только цифры).",
            reply_markup=create_back_keyboard("clientmap_add"),
        )
        await state.set_state(VPNSetup.entering_client_mapping_user_id)
        await callback.answer()
        return

    if data.startswith("clientmap_add_for_"):
        telegram_id = data.removeprefix("clientmap_add_for_")
        if not telegram_id.isdigit():
            await callback.answer("Некорректный ID", show_alert=True)
            return
        clients = await get_all_clients_unique()
        if not clients:
            await callback.message.edit_text(
                "❌ Нет ни одного клиента OpenVPN/WireGuard для привязки.",
                reply_markup=create_back_keyboard("clients_menu"),
            )
            await callback.answer()
            return
        total_pages = max(1, (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        await callback.message.edit_text(
            f"Пользователь: <code>{get_user_label(telegram_id)}</code>\n\n"
            "Выберите VPN-клиента для привязки:",
            reply_markup=create_clientmap_client_list_menu(
                telegram_id=telegram_id,
                clients=clients,
                page=1,
                total_pages=total_pages,
            ),
        )
        await callback.answer()
        return

    if data.startswith("clientmap_clients_p_"):
        payload = data.removeprefix("clientmap_clients_p_")
        if "_" not in payload:
            await callback.answer("Некорректные данные", show_alert=True)
            return
        telegram_id, page_raw = payload.rsplit("_", 1)
        if not telegram_id.isdigit() or not page_raw.isdigit():
            await callback.answer("Некорректные данные", show_alert=True)
            return
        page = int(page_raw)
        clients = await get_all_clients_unique()
        total_pages = max(1, (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        page = max(1, min(page, total_pages))
        await callback.message.edit_text(
            f"Пользователь: <code>{get_user_label(telegram_id)}</code>\n\n"
            "Выберите VPN-клиента для привязки:",
            reply_markup=create_clientmap_client_list_menu(
                telegram_id=telegram_id,
                clients=clients,
                page=page,
                total_pages=total_pages,
            ),
        )
        await callback.answer()
        return

    if data.startswith("clientmap_bind_"):
        payload = data.removeprefix("clientmap_bind_")
        if "_" not in payload:
            await callback.answer("Некорректные данные", show_alert=True)
            return
        telegram_id, client_name = payload.split("_", 1)
        if not telegram_id.isdigit() or not client_name:
            await callback.answer("Некорректные данные", show_alert=True)
            return

        mapping = get_client_mapping()
        user_clients = mapping.get(telegram_id, [])
        if client_name in user_clients:
            await callback.answer("Эта привязка уже существует.", show_alert=True)
        else:
            add_client_mapping(telegram_id, client_name)
            mapping = get_client_mapping()
            total_count = len(mapping.get(telegram_id, []))
            await callback.message.edit_text(
                "✅ Привязка сохранена.\n\n"
                f"Пользователь: <code>{get_user_label(telegram_id)}</code>\n"
                f"Клиент: <b>{client_name}</b>\n"
                f"Всего клиентов у пользователя: <b>{total_count}</b>",
                reply_markup=create_back_keyboard(f"clientmap_user_{telegram_id}"),
            )
        await callback.answer()
        return
    
    if data.startswith("clientmap_delete_confirm_"):
        payload = data.removeprefix("clientmap_delete_confirm_")
        if "_" not in payload:
            await callback.answer("Некорректные данные", show_alert=True)
            return
        telegram_id, client_name = payload.split("_", 1)
        from ..keyboards import clients_menu_page_for_telegram_id

        return_page = clients_menu_page_for_telegram_id(telegram_id, client_name)
        remove_client_mapping(telegram_id, client_name)
        client_names = get_client_mapping().get(telegram_id, [])
        if client_names:
            if len(client_names) == 1:
                from ..keyboards import create_client_protocols_menu, clients_menu_page_for_telegram_id

                return_page = clients_menu_page_for_telegram_id(telegram_id)
                await callback.message.edit_text(
                    f"Привязка удалена.\n\n"
                    f"Настройка клиента <code>{get_user_label(telegram_id)}</code> → "
                    f"<b>{client_names[0]}</b>\n\n"
                    "Настройка протоколов:",
                    reply_markup=create_client_protocols_menu(
                        telegram_id,
                        client_names[0],
                        f"clients_p_{return_page}",
                    ),
                )
            else:
                await callback.message.edit_text(
                    f"Привязка удалена.\n\nПользователь: <code>{get_user_label(telegram_id)}</code>\n"
                    f"Привязок: <b>{len(client_names)}</b>\n\n"
                    "Выберите клиента для настройки:",
                    reply_markup=create_client_user_menu(telegram_id, client_names, 1),
                )
        else:
            mapping = get_client_mapping()
            total_users = len(mapping)
            total_bindings = sum(len(names) for names in mapping.values())
            total_pages = (
                max(1, (total_users + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE) if total_users else 1
            )
            show_page = max(1, min(return_page, total_pages))
            await callback.message.edit_text(
                "Привязка удалена.\n\n"
                + get_clients_menu_text(total_users, show_page, total_bindings),
                reply_markup=create_clients_menu(admin_ids, show_page),
            )
        await callback.answer()
        return

    if data.startswith("clientmap_delete_"):
        payload = data.removeprefix("clientmap_delete_")
        if "_" not in payload:
            await callback.answer("Некорректные данные", show_alert=True)
            return
        telegram_id, client_name = payload.split("_", 1)
        client_map = get_client_mapping()
        client_names = client_map.get(telegram_id, [])
        has_mapping = client_name in client_names
        if not has_mapping:
            mapping = get_client_mapping()
            total_users = len(mapping)
            total_bindings = sum(len(names) for names in mapping.values())
            await callback.message.edit_text(
                "Привязка не найдена.\n\n"
                + get_clients_menu_text(total_users, 1, total_bindings),
                reply_markup=create_clients_menu(admin_ids, 1),
            )
            await callback.answer()
            return
        await callback.message.edit_text(
            f"Удалить привязку <code>{get_user_label(telegram_id)}</code> → "
            f"<b>{client_name}</b>?",
            reply_markup=create_clientmap_delete_menu(telegram_id, client_name),
        )
        await callback.answer()
        return

    if data.startswith("clientmap_user_"):
        telegram_id = data.removeprefix("clientmap_user_")
        client_names = get_client_mapping().get(telegram_id, [])
        if not client_names:
            mapping = get_client_mapping()
            total_users = len(mapping)
            total_bindings = sum(len(names) for names in mapping.values())
            await callback.message.edit_text(
                "Пользователь или привязки не найдены.\n\n"
                + get_clients_menu_text(total_users, 1, total_bindings),
                reply_markup=create_clients_menu(admin_ids, 1),
            )
            await callback.answer()
            return
        if len(client_names) == 1:
            from ..keyboards import create_client_protocols_menu, clients_menu_page_for_telegram_id

            return_page = clients_menu_page_for_telegram_id(telegram_id)
            await callback.message.edit_text(
                f"Настройка клиента <code>{get_user_label(telegram_id)}</code> → <b>{client_names[0]}</b>\n\n"
                "Настройка протоколов:",
                reply_markup=create_client_protocols_menu(
                    telegram_id,
                    client_names[0],
                    f"clients_p_{return_page}",
                ),
            )
            await callback.answer()
            return
        await callback.message.edit_text(
            f"Пользователь: <code>{get_user_label(telegram_id)}</code>\n"
            f"Привязок: <b>{len(client_names)}</b>\n\n"
            "Выберите клиента для настройки:",
            reply_markup=create_client_user_menu(telegram_id, client_names, 1),
        )
        await callback.answer()
        return

    if data.startswith("clientmap_"):
        payload = data.removeprefix("clientmap_")
        if "_" not in payload:
            await callback.answer("Некорректные данные", show_alert=True)
            return
        telegram_id, client_name = payload.split("_", 1)
        client_map = get_client_mapping()
        client_names = client_map.get(telegram_id, [])
        if client_name not in client_names:
            mapping = get_client_mapping()
            total_users = len(mapping)
            total_bindings = sum(len(names) for names in mapping.values())
            await callback.message.edit_text(
                "Привязка не найдена.\n\n"
                + get_clients_menu_text(total_users, 1, total_bindings),
                reply_markup=create_clients_menu(admin_ids, 1),
            )
            await callback.answer()
            return
        from ..keyboards import create_client_protocols_menu

        await callback.message.edit_text(
            f"Настройка клиента <code>{get_user_label(telegram_id)}</code> → <b>{client_name}</b>\n\n"
            "Настройка протоколов:",
            reply_markup=create_client_protocols_menu(
                telegram_id,
                client_name,
                f"clientmap_user_{telegram_id}",
            ),
        )
        await callback.answer()
        return

    if data.startswith("client_proto_menu_"):
        telegram_id = data.split("_", 3)[3]
        client_entries = get_client_mapping_entries()
        client_name = next((name for tid, name in client_entries if tid == telegram_id), None)
        if not client_name:
            mapping = get_client_mapping()
            total_users = len(mapping)
            total_bindings = sum(len(names) for names in mapping.values())
            await callback.message.edit_text(
                "Привязка не найдена.\n\n"
                + get_clients_menu_text(total_users, 1, total_bindings),
                reply_markup=create_clients_menu(admin_ids, 1),
            )
            await callback.answer()
            return
        from ..keyboards import create_client_protocols_transport_menu

        await callback.message.edit_text(
            f"Настройка клиента <code>{get_user_label(telegram_id)}</code> → <b>{client_name}</b>\n\n"
            "Настройка протоколов:",
            reply_markup=create_client_protocols_transport_menu(
                telegram_id,
                client_name,
                f"clientmap_user_{telegram_id}",
            ),
        )
        await callback.answer()
        return


@router.callback_query(
    lambda c: c.data == "pending_requests_menu"
    or (
        c.data.startswith("pending_p_") and c.data.removeprefix("pending_p_").isdigit()
    )
)
async def handle_pending_requests_nav(callback: types.CallbackQuery, state: FSMContext):
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return

    await state.clear()
    page = 1
    if callback.data.startswith("pending_p_"):
        page = int(callback.data.removeprefix("pending_p_"))

    user_ids = get_pending_request_user_ids()
    count = len(user_ids)
    total_pages = (
        max(1, (count + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE) if count else 1
    )
    page = max(1, min(page, total_pages))

    await callback.message.edit_text(
        get_pending_requests_menu_text(count, page),
        reply_markup=create_pending_requests_menu(page),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("pending_req_"))
async def handle_pending_request_open(callback: types.CallbackQuery, state: FSMContext):
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return

    uid = callback.data.removeprefix("pending_req_")
    if not uid.isdigit():
        await callback.answer("Некорректные данные", show_alert=True)
        return

    if uid not in get_pending_request_user_ids():
        count = get_pending_requests_count()
        await callback.message.edit_text(
            "Запрос уже обработан или отсутствует.\n\n"
            + get_pending_requests_menu_text(count, 1),
            reply_markup=create_pending_requests_menu(1),
        )
        await callback.answer()
        return

    await state.clear()
    text, suggested = format_pending_request_admin_text(uid)
    await callback.message.edit_text(
        text,
        reply_markup=create_request_actions_keyboard(int(uid), suggested),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "pending_noop")
async def handle_pending_noop(callback: types.CallbackQuery):
    if callback.from_user.id not in get_admin_ids():
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    await callback.answer()


def _banned_list_text(count: int) -> str:
    base = (
        "🚫 <b>Заблокированные</b>\n\n"
        "Бот не отвечает этим пользователям.\n"
        "Нажмите строку, чтобы снять блокировку, или добавьте новый ID."
    )
    if count:
        return f"{base}\n\nВ списке: <b>{count}</b>"
    return base


def _parse_ban_rm_callback(data: str) -> Optional[Tuple[str, int]]:
    if not data.startswith("ban_rm_"):
        return None
    rest = data.removeprefix("ban_rm_")
    if "_" in rest:
        uid_str, page_str = rest.rsplit("_", 1)
        if uid_str.isdigit() and page_str.isdigit():
            return uid_str, int(page_str)
    if rest.isdigit():
        return rest, 1
    return None


@router.callback_query(
    lambda c: c.data == "banned_menu"
    or (c.data.startswith("banned_p_") and c.data.removeprefix("banned_p_").isdigit())
)
async def handle_banned_list_nav(callback: types.CallbackQuery, state: FSMContext):
    """Список заблокированных пользователей и пагинация."""
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return

    await state.clear()
    page = 1
    if callback.data.startswith("banned_p_"):
        page = int(callback.data.removeprefix("banned_p_"))

    sorted_ids = sorted(get_banned_user_ids())
    total_pages = (
        max(1, (len(sorted_ids) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        if sorted_ids
        else 1
    )
    page = max(1, min(page, total_pages))

    await callback.message.edit_text(
        _banned_list_text(len(sorted_ids)),
        reply_markup=create_banned_list_keyboard(sorted_ids, page),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("ban_rm_"))
async def handle_ban_remove(callback: types.CallbackQuery, state: FSMContext):
    """Снять пользователя с бан-листа."""
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return

    parsed = _parse_ban_rm_callback(callback.data)
    if not parsed:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    uid_str, return_page = parsed
    uid = int(uid_str)

    if not is_user_banned(uid):
        await callback.answer("Уже не в списке", show_alert=True)
        sorted_ids = sorted(get_banned_user_ids())
        total_pages = (
            max(1, (len(sorted_ids) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
            if sorted_ids
            else 1
        )
        show_page = max(1, min(return_page, total_pages))
        await callback.message.edit_text(
            _banned_list_text(len(sorted_ids)),
            reply_markup=create_banned_list_keyboard(sorted_ids, show_page),
        )
        return

    unban_user(uid)
    log_action(
        "bot",
        callback.from_user.id,
        callback.from_user.full_name,
        "user_unban",
        uid_str,
    )

    sorted_ids = sorted(get_banned_user_ids())
    total_pages = (
        max(1, (len(sorted_ids) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        if sorted_ids
        else 1
    )
    show_page = max(1, min(return_page, total_pages))

    await callback.message.edit_text(
        _banned_list_text(len(sorted_ids)),
        reply_markup=create_banned_list_keyboard(sorted_ids, show_page),
    )
    await callback.answer("Разблокировано")


@router.callback_query(lambda c: c.data == "ban_add")
async def handle_ban_add_prompt(callback: types.CallbackQuery, state: FSMContext):
    """Запрос ID для добавления в бан-лист."""
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return

    await state.set_state(VPNSetup.entering_ban_user_id)
    await callback.message.edit_text(
        "Введите <b>числовой Telegram ID</b> пользователя для блокировки.\n"
        "Бот перестанет отвечать ему на команды и кнопки.\n\n"
        "Администраторов заблокировать нельзя.",
        reply_markup=create_back_keyboard("banned_menu"),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "banned_noop")
async def handle_banned_noop(callback: types.CallbackQuery):
    if callback.from_user.id not in get_admin_ids():
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    await callback.answer()


@router.message(VPNSetup.entering_ban_user_id)
async def handle_ban_user_id_input(message: types.Message, state: FSMContext):
    """Добавление пользователя в бан-лист по введённому ID."""
    admin_ids = get_admin_ids()
    if message.from_user.id not in admin_ids:
        await state.clear()
        return

    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Нужен только числовой Telegram ID (цифры).")
        return

    uid = int(text)
    if uid in admin_ids:
        await message.answer("Нельзя заблокировать администратора.")
        return

    if is_user_banned(uid):
        await message.answer("Этот пользователь уже в списке блокировки.")
        return

    remove_client_mapping(str(uid))
    ban_user(uid)
    log_action(
        "bot",
        message.from_user.id,
        message.from_user.full_name,
        "user_ban",
        str(uid),
    )
    await state.clear()

    sorted_ids = sorted(get_banned_user_ids())
    idx = sorted_ids.index(uid)
    page = idx // ITEMS_PER_PAGE + 1

    await message.answer(
        f"Пользователь <code>{uid}</code> заблокирован.",
        reply_markup=create_banned_list_keyboard(sorted_ids, page),
    )


@router.message(VPNSetup.entering_client_mapping_user_id)
async def handle_client_mapping_user_id_input(message: types.Message, state: FSMContext):
    """Обработка ручного ввода Telegram ID для мастера привязки."""
    admin_ids = get_admin_ids()
    if message.from_user.id not in admin_ids:
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Введите только числовой Telegram ID.")
        return
    await state.clear()
    clients = await get_all_clients_unique()
    if not clients:
        await message.answer(
            "❌ Нет ни одного клиента OpenVPN/WireGuard для привязки.",
            reply_markup=create_back_keyboard("clients_menu"),
        )
        return
    total_pages = max(1, (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    await message.answer(
        f"Пользователь: <code>{get_user_label(text)}</code>\n\n"
        "Выберите VPN-клиента для привязки:",
        reply_markup=create_clientmap_client_list_menu(
            telegram_id=text,
            clients=clients,
            page=1,
            total_pages=total_pages,
        ),
    )


@router.callback_query(
    lambda c: c.data in [
        "notifications_menu",
        "toggle_notifications",
        "toggle_load_notifications",
        "toggle_request_notifications",
        "toggle_vpn_service_notifications",
    ]
)
async def handle_notifications_menu(callback: types.CallbackQuery):
    """Обработка меню уведомлений."""
    admin_ids = get_admin_ids()
    
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    
    if callback.data == "toggle_notifications":
        current = is_admin_notification_enabled(callback.from_user.id)
        set_admin_notification(callback.from_user.id, not current)
    elif callback.data == "toggle_load_notifications":
        current = is_admin_load_notification_enabled(callback.from_user.id)
        set_admin_load_notification(callback.from_user.id, not current)
    elif callback.data == "toggle_request_notifications":
        current = is_admin_request_notification_enabled(callback.from_user.id)
        set_admin_request_notification(callback.from_user.id, not current)
    elif callback.data == "toggle_vpn_service_notifications":
        current = is_admin_vpn_service_notification_enabled(callback.from_user.id)
        set_admin_vpn_service_notification(callback.from_user.id, not current)
    
    await callback.message.edit_text(
        "Настройка уведомлений:",
        reply_markup=create_notifications_menu(callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("toggle_proto_"))
async def handle_toggle_protocol(callback: types.CallbackQuery):
    """Обработка переключения доступных протоколов для клиента."""
    admin_ids = get_admin_ids()

    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return

    from ..config import get_client_allowed_protocols, set_client_allowed_protocols
    from ..keyboards import create_client_protocols_menu

    data = callback.data
    telegram_id = None

    # Получаем текущие настройки
    if data.startswith("toggle_proto_ovpn_vpn_"):
        telegram_id = data.split("_", 4)[4]
        protocols = get_client_allowed_protocols(telegram_id)
        set_client_allowed_protocols(
            telegram_id,
            openvpn_vpn=not protocols.get("openvpn_vpn", True),
            openvpn_antizapret=protocols.get("openvpn_antizapret", True),
            wireguard_vpn=protocols.get("wireguard_vpn", True),
            wireguard_antizapret=protocols.get("wireguard_antizapret", True)
        )
    elif data.startswith("toggle_proto_ovpn_az_"):
        telegram_id = data.split("_", 4)[4]
        protocols = get_client_allowed_protocols(telegram_id)
        set_client_allowed_protocols(
            telegram_id,
            openvpn_vpn=protocols.get("openvpn_vpn", True),
            openvpn_antizapret=not protocols.get("openvpn_antizapret", True),
            wireguard_vpn=protocols.get("wireguard_vpn", True),
            wireguard_antizapret=protocols.get("wireguard_antizapret", True)
        )
    elif data.startswith("toggle_proto_wg_vpn_"):
        telegram_id = data.split("_", 4)[4]
        protocols = get_client_allowed_protocols(telegram_id)
        set_client_allowed_protocols(
            telegram_id,
            openvpn_vpn=protocols.get("openvpn_vpn", True),
            openvpn_antizapret=protocols.get("openvpn_antizapret", True),
            wireguard_vpn=not protocols.get("wireguard_vpn", True),
            wireguard_antizapret=protocols.get("wireguard_antizapret", True)
        )
    elif data.startswith("toggle_proto_wg_az_"):
        telegram_id = data.split("_", 4)[4]
        protocols = get_client_allowed_protocols(telegram_id)
        set_client_allowed_protocols(
            telegram_id,
            openvpn_vpn=protocols.get("openvpn_vpn", True),
            openvpn_antizapret=protocols.get("openvpn_antizapret", True),
            wireguard_vpn=protocols.get("wireguard_vpn", True),
            wireguard_antizapret=not protocols.get("wireguard_antizapret", True)
        )
    elif data.startswith("toggle_proto_ovpn_default_"):
        telegram_id = data.split("_", 4)[4]
        protocols = get_client_allowed_protocols(telegram_id)
        next_default = not protocols.get("openvpn_default", True)
        next_tcp = protocols.get("openvpn_tcp", True)
        next_udp = protocols.get("openvpn_udp", True)
        disable_openvpn_sections = not next_default and not next_tcp and not next_udp
        set_client_allowed_protocols(
            telegram_id,
            openvpn_default=next_default,
            openvpn_vpn=False if disable_openvpn_sections else protocols.get("openvpn_vpn", True),
            openvpn_antizapret=False if disable_openvpn_sections else protocols.get("openvpn_antizapret", True),
        )
    elif data.startswith("toggle_proto_ovpn_tcp_"):
        telegram_id = data.split("_", 4)[4]
        protocols = get_client_allowed_protocols(telegram_id)
        new_tcp = not protocols.get("openvpn_tcp", True)
        new_udp = protocols.get("openvpn_udp", True)
        current_default = protocols.get("openvpn_default", True)
        disable_openvpn_sections = not current_default and not new_tcp and not new_udp
        set_client_allowed_protocols(
            telegram_id,
            openvpn_tcp=new_tcp,
            openvpn_default=current_default,
            openvpn_vpn=False if disable_openvpn_sections else protocols.get("openvpn_vpn", True),
            openvpn_antizapret=False if disable_openvpn_sections else protocols.get("openvpn_antizapret", True),
        )
    elif data.startswith("toggle_proto_ovpn_udp_"):
        telegram_id = data.split("_", 4)[4]
        protocols = get_client_allowed_protocols(telegram_id)
        new_udp = not protocols.get("openvpn_udp", True)
        new_tcp = protocols.get("openvpn_tcp", True)
        current_default = protocols.get("openvpn_default", True)
        disable_openvpn_sections = not current_default and not new_tcp and not new_udp
        set_client_allowed_protocols(
            telegram_id,
            openvpn_udp=new_udp,
            openvpn_default=current_default,
            openvpn_vpn=False if disable_openvpn_sections else protocols.get("openvpn_vpn", True),
            openvpn_antizapret=False if disable_openvpn_sections else protocols.get("openvpn_antizapret", True),
        )
    elif data.startswith("toggle_proto_wg_type_wg_"):
        telegram_id = data.split("_", 5)[5]
        protocols = get_client_allowed_protocols(telegram_id)
        new_wg = not protocols.get("wireguard_wg", True)
        new_am = protocols.get("wireguard_am", True)
        disable_wireguard_sections = not new_wg and not new_am
        set_client_allowed_protocols(
            telegram_id,
            wireguard_wg=new_wg,
            wireguard_vpn=False if disable_wireguard_sections else protocols.get("wireguard_vpn", True),
            wireguard_antizapret=False if disable_wireguard_sections else protocols.get("wireguard_antizapret", True),
        )
    elif data.startswith("toggle_proto_wg_type_am_"):
        telegram_id = data.split("_", 5)[5]
        protocols = get_client_allowed_protocols(telegram_id)
        new_am = not protocols.get("wireguard_am", True)
        new_wg = protocols.get("wireguard_wg", True)
        disable_wireguard_sections = not new_wg and not new_am
        set_client_allowed_protocols(
            telegram_id,
            wireguard_am=new_am,
            wireguard_vpn=False if disable_wireguard_sections else protocols.get("wireguard_vpn", True),
            wireguard_antizapret=False if disable_wireguard_sections else protocols.get("wireguard_antizapret", True),
        )
    else:
        await callback.answer()
        return

    if not telegram_id:
        await callback.answer()
        return

    client_entries = get_client_mapping_entries()
    client_name = next((name for tid, name in client_entries if tid == telegram_id), "неизвестен")

    await callback.message.edit_text(
        f"Настройка клиента <code>{get_user_label(telegram_id)}</code> → <b>{client_name}</b>\n\n"
        "Настройка протоколов:",
        reply_markup=create_client_protocols_menu(
            telegram_id,
            client_name,
            f"clientmap_user_{telegram_id}",
        ),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "no_action" or c.data == "no_protocols")
async def handle_no_action(callback: types.CallbackQuery):
    """Обработка кнопок без действия."""
    if callback.data == "no_protocols":
        await callback.answer("У вас нет доступных протоколов. Обратитесь к администратору.", show_alert=True)
    else:
        await callback.answer()
    await callback.answer("В разработке", show_alert=False)
