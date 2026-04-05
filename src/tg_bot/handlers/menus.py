"""Обработчики навигации по меню."""

from typing import Optional, Tuple

from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from ..config import (
    ITEMS_PER_PAGE,
    get_admin_ids,
    get_client_mapping,
    remove_client_mapping,
    get_banned_user_ids,
    ban_user,
    unban_user,
    is_user_banned,
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
    create_openvpn_menu,
    create_wireguard_menu,
    create_server_menu,
    create_clients_menu,
    create_banned_list_keyboard,
    create_admins_menu,
    create_notifications_menu,
    create_clientmap_delete_menu,
    create_back_keyboard,
)
from ..states import VPNSetup
from ..utils import get_external_ip
from ..audit import log_action

router = Router()


def _get_server_ip():
    return get_external_ip()


@router.callback_query(
    lambda c: c.data in [
        "main_menu",
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
    elif callback.data == "openvpn_menu":
        await callback.message.edit_text("Меню OpenVPN:", reply_markup=create_openvpn_menu())
    elif callback.data == "server_menu":
        await callback.message.edit_text("Меню сервера:", reply_markup=create_server_menu())
    elif callback.data == "clients_menu":
        await state.clear()
        await callback.message.edit_text(
            "Привязки клиентов:\n\n"
            "Чтобы удалить привязку — нажмите на неё в списке и подтвердите удаление.\n"
            "Раздел «Заблокированные» — пользователи, которым бот не отвечает.",
            reply_markup=create_clients_menu(admin_ids),
        )
    elif callback.data == "admins_menu":
        await callback.message.edit_text("Администраторы:", reply_markup=create_admins_menu(admin_ids))
    else:
        await callback.message.edit_text("Меню WireGuard:", reply_markup=create_wireguard_menu())
    
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("clientmap_"))
async def handle_clientmap_actions(callback: types.CallbackQuery, state: FSMContext):
    """Обработка действий с привязками клиентов."""
    admin_ids = get_admin_ids()
    
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    
    data = callback.data
    
    if data == "clientmap_add":
        await callback.message.edit_text(
            "Отправьте привязку в формате:\n"
            "<code>client_id:имя_клиента</code>\n"
            "Например: <code>123456789:vpn-user</code>",
            reply_markup=create_back_keyboard("clients_menu"),
        )
        await state.set_state(VPNSetup.entering_client_mapping)
        await callback.answer()
        return
    
    if data.startswith("clientmap_delete_confirm_"):
        telegram_id = data.split("_")[-1]
        remove_client_mapping(telegram_id)
        await callback.message.edit_text(
            "Привязка удалена.", reply_markup=create_clients_menu(admin_ids)
        )
        await callback.answer()
        return
    
    if data.startswith("clientmap_"):
        telegram_id = data.split("_", 1)[1]
        client_map = get_client_mapping()
        client_name = client_map.get(telegram_id)
        if not client_name:
            await callback.message.edit_text(
                "Привязка не найдена.", reply_markup=create_clients_menu(admin_ids)
            )
            await callback.answer()
            return
        await callback.message.edit_text(
            f"Удалить привязку <code>{get_user_label(telegram_id)}</code> → "
            f"<b>{client_name}</b>?",
            reply_markup=create_clientmap_delete_menu(telegram_id, client_name),
        )
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


@router.callback_query(lambda c: c.data == "no_action")
async def handle_no_action(callback: types.CallbackQuery):
    """Обработка кнопок без действия."""
    await callback.answer("В разработке", show_alert=False)
