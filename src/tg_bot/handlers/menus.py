"""Обработчики навигации по меню."""

from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from ..config import get_admin_ids, get_client_mapping, remove_client_mapping
from ..admin import (
    is_admin_notification_enabled,
    set_admin_notification,
    is_admin_load_notification_enabled,
    set_admin_load_notification,
    is_admin_request_notification_enabled,
    set_admin_request_notification,
    get_user_label,
)
from ..keyboards import (
    create_main_menu,
    create_openvpn_menu,
    create_wireguard_menu,
    create_server_menu,
    create_clients_menu,
    create_admins_menu,
    create_notifications_menu,
    create_clientmap_delete_menu,
    create_back_keyboard,
)
from ..states import VPNSetup
from ..utils import get_external_ip

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
async def handle_main_menus(callback: types.CallbackQuery):
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
        await callback.message.edit_text(
            "Привязки клиентов:\n\n"
            "Чтобы удалить привязку — нажмите на неё в списке и подтвердите удаление.",
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


@router.callback_query(
    lambda c: c.data in [
        "notifications_menu",
        "toggle_notifications",
        "toggle_load_notifications",
        "toggle_request_notifications",
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
    
    await callback.message.edit_text(
        "Настройка уведомлений:",
        reply_markup=create_notifications_menu(callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "no_action")
async def handle_no_action(callback: types.CallbackQuery):
    """Обработка кнопок без действия."""
    await callback.answer("В разработке", show_alert=False)
