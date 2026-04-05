"""Обработчики общих команд."""

import re

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ..config import get_admin_ids, get_client_name_for_user, set_client_mapping
from ..admin import update_admin_info, is_admin_request_notification_enabled
from ..keyboards import (
    create_main_menu,
    create_client_menu,
    create_request_access_keyboard,
    create_request_actions_keyboard,
)
from ..states import VPNSetup
from ..utils import get_external_ip

router = Router()


def _suggest_client_name(user: types.User) -> str:
    """Предложить имя клиента по данным пользователя Telegram (username / first_name / user_id)."""
    name = (user.username or "").strip()
    if name and re.match(r"^[a-zA-Z0-9_-]{1,32}$", name):
        return name
    name = " ".join([p for p in [user.first_name, user.last_name] if p]).strip()
    if name:
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:32]
        if sanitized:
            return sanitized
    return f"user_{user.id}"


def _get_server_ip():
    return get_external_ip()


async def show_client_menu(message: types.Message, user_id: int):
    """Показать меню клиента для пользователей не-администраторов."""
    client_name = get_client_name_for_user(user_id)
    if not client_name:
        await message.answer(
            "У вас ещё нет доступа к боту.\n\n"
            f"Ваш ID: <code>{user_id}</code>\n\n"
            "Нажмите кнопку ниже — администратор получит запрос и сможет "
            "подтвердить или отклонить доступ.",
            reply_markup=create_request_access_keyboard(),
        )
        return
    await message.answer(
        f'Ваш клиент: "{client_name}". Выберите протокол:',
        reply_markup=create_client_menu(client_name),
    )


@router.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    """Обработка команды /start."""
    update_admin_info(message.from_user)
    admin_ids = get_admin_ids()
    
    if not admin_ids:
        await message.answer(
            "Администраторы еще не настроены.\n"
            "Ваш ID для настройки: "
            f"<code>{message.from_user.id}</code>\n"
            "Добавьте его в переменную <b>ADMIN_ID</b> в .env."
        )
        await state.clear()
        return

    # Неадмин без привязки — показываем кнопку «Запросить доступ»
    if message.from_user.id not in admin_ids:
        client_name = get_client_name_for_user(message.from_user.id)
        if not client_name:
            await message.answer(
                "У вас ещё нет доступа к боту.\n\n"
                f"Ваш ID: <code>{message.from_user.id}</code>\n\n"
                "Нажмите кнопку ниже — администратор получит запрос и сможет "
                "подтвердить или отклонить доступ.",
                reply_markup=create_request_access_keyboard(),
            )
            await state.clear()
            return
        await show_client_menu(message, message.from_user.id)
        await state.clear()
        return
    
    # Админ
    server_ip = _get_server_ip()
    await message.answer("Главное меню:", reply_markup=create_main_menu(server_ip))
    await state.set_state(VPNSetup.choosing_option)


@router.message(Command("id"))
async def show_user_id(message: types.Message):
    """Обработка команды /id."""
    update_admin_info(message.from_user)
    await message.answer(f"Ваш ID: <code>{message.from_user.id}</code>")


@router.message(Command("request"))
async def request_access_command(message: types.Message):
    """Обработка /request — запрос доступа (то же, что кнопка «Запросить доступ»)."""
    update_admin_info(message.from_user)
    admin_ids = get_admin_ids()
    if not admin_ids:
        await message.answer("Администраторы не настроены.")
        return
    if message.from_user.id in admin_ids:
        await message.answer("Вы уже администратор.")
        return
    if get_client_name_for_user(message.from_user.id):
        await message.answer("У вас уже есть доступ. Используйте /start.")
        return
    user = message.from_user
    label = " ".join([p for p in [user.first_name, user.last_name] if p]).strip() or "—"
    username_part = f" @{user.username}" if user.username else ""
    text = (
        f"Клиент: {label}{username_part}\n"
        f"ID: <code>{user.id}</code>\n\n"
        "Выберите клиента, введите имя клиента или отклоните запрос."
    )
    keyboard = create_request_actions_keyboard(user.id)
    from ..bot import get_bot
    bot = get_bot()
    sent = 0
    for admin_id in admin_ids:
        if not is_admin_request_notification_enabled(admin_id):
            continue
        try:
            await bot.send_message(admin_id, text, reply_markup=keyboard)
            sent += 1
        except Exception:
            pass
    if sent:
        await message.answer("Запрос отправлен администраторам.")


@router.message(Command("client"))
async def handle_client_mapping_command(message: types.Message, state: FSMContext):
    """Обработка команды /client для привязки клиентов."""
    update_admin_info(message.from_user)
    admin_ids = get_admin_ids()
    
    if message.from_user.id not in admin_ids:
        await message.answer("Доступ запрещен")
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Отправьте привязку в формате:\n"
            "<code>client_id:имя_клиента</code>\n"
            "Например: <code>123456789:vpn-user</code>"
        )
        await state.set_state(VPNSetup.entering_client_mapping)
        return
    
    await process_client_mapping(message, parts[1], state)


@router.message(VPNSetup.entering_client_mapping)
async def handle_client_mapping_state(message: types.Message, state: FSMContext):
    """Обработка ввода привязки клиента (состояние FSM)."""
    update_admin_info(message.from_user)
    admin_ids = get_admin_ids()
    
    if message.from_user.id not in admin_ids:
        await message.answer("Доступ запрещен")
        await state.clear()
        return
    
    from ..keyboards import create_clients_menu
    success = await process_client_mapping(message, message.text, state)
    if success:
        await message.answer(
            "Привязки клиентов:\n\n"
            "Чтобы удалить привязку — нажмите на неё в списке и подтвердите удаление.",
            reply_markup=create_clients_menu(admin_ids),
        )


async def process_client_mapping(message: types.Message, raw_text: str, state: FSMContext):
    """Обработать введённую привязку клиента."""
    payload = raw_text.strip()
    match = re.match(r"^(\d+)\s*:\s*([a-zA-Z0-9_-]{1,32})$", payload)
    if not match:
        await message.answer(
            "❌ Некорректный формат. Используйте:\n"
            "<code>client_id:имя_клиента</code>"
        )
        return False
    
    telegram_id, client_name = match.groups()
    set_client_mapping(telegram_id, client_name)
    # Уведомляем клиента о привязке
    try:
        from ..bot import get_bot
        bot = get_bot()
        await bot.send_message(
            int(telegram_id),
            f"✅ Вам предоставлен доступ к боту. Ваш клиент: <b>{client_name}</b>. Нажмите /start для входа.",
        )
    except Exception:
        pass
    await message.answer(
        f"✅ Привязка сохранена: <code>{telegram_id}</code> → <b>{client_name}</b>"
    )
    await state.clear()
    return True


@router.callback_query(lambda c: c.data == "request_access")
async def handle_request_access(callback: types.CallbackQuery):
    """При нажатии неавторизованным пользователем «Запросить доступ» — уведомить всех админов."""
    user = callback.from_user
    admin_ids = get_admin_ids()
    if not admin_ids:
        await callback.answer("Администраторы не настроены.", show_alert=True)
        return
    if user.id in admin_ids:
        await callback.answer("Вы уже администратор.", show_alert=True)
        return
    if get_client_name_for_user(user.id):
        await callback.answer("У вас уже есть доступ.", show_alert=True)
        return

    label = " ".join([p for p in [user.first_name, user.last_name] if p]).strip() or "—"
    username_part = f" @{user.username}" if user.username else ""
    text = (
        f"Клиент: {label}{username_part}\n"
        f"ID: <code>{user.id}</code>\n\n"
        "Выберите клиента, введите имя клиента или отклоните запрос."
    )
    keyboard = create_request_actions_keyboard(user.id)

    from ..bot import get_bot
    bot = get_bot()
    sent = 0
    for admin_id in admin_ids:
        if not is_admin_request_notification_enabled(admin_id):
            continue
        try:
            await bot.send_message(admin_id, text, reply_markup=keyboard)
            sent += 1
        except Exception:
            pass
    if sent:
        await callback.answer("Запрос отправлен администраторам.")
    else:
        try:
            await callback.answer()
        except Exception:
            pass
