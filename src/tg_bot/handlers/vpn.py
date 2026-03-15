"""Обработчики управления клиентами VPN."""

import os
import re
import asyncio

from aiogram import Router, types
from aiogram.types import FSInputFile
from aiogram.fsm.context import FSMContext

from ..config import get_admin_ids, get_client_name_for_user, ITEMS_PER_PAGE
from ..admin import update_admin_info
from ..keyboards import (
    create_main_menu,
    create_client_menu,
    create_openvpn_config_menu,
    create_wireguard_config_menu,
    create_openvpn_protocol_menu,
    create_wireguard_type_menu,
    create_client_list_keyboard,
    create_confirmation_keyboard,
    create_rename_confirmation_keyboard,
)
from ..states import VPNSetup
from ..utils import execute_script, get_clients, cleanup_openvpn_files, get_external_ip
from ..audit import log_action, notify_admins

router = Router()


def _get_server_ip():
    return get_external_ip()


async def _get_bot():
    """Получить экземпляр бота (ленивая инициализация)."""
    from ..bot import get_bot
    return get_bot()


@router.callback_query(lambda c: c.data.startswith("client_"))
async def handle_client_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора клиента для скачивания конфига."""
    admin_ids = get_admin_ids()
    _, vpn_type, client_name = callback.data.split("_", 2)
    
    if callback.from_user.id not in admin_ids:
        allowed_client = get_client_name_for_user(callback.from_user.id)
        if not allowed_client or allowed_client != client_name:
            await callback.answer("Доступ запрещен!", show_alert=True)
            return
        await state.update_data(client_mode=True)
    
    await state.update_data(client_name=client_name, vpn_type=vpn_type)
    
    back_callback = (
        "back_to_client_menu"
        if callback.from_user.id not in admin_ids
        else "back_to_client_list"
    )
    
    if vpn_type == "openvpn":
        await callback.message.edit_text(
            "Выберите тип конфигурации OpenVPN:",
            reply_markup=create_openvpn_config_menu(client_name, back_callback),
        )
        await state.set_state(VPNSetup.choosing_config_type)
    else:
        await callback.message.edit_text(
            "Выберите тип конфигурации WireGuard:",
            reply_markup=create_wireguard_config_menu(client_name, back_callback),
        )
        await state.set_state(VPNSetup.choosing_config_type)
    
    await callback.answer()


@router.callback_query(VPNSetup.choosing_config_type)
async def handle_interface_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора интерфейса/типа конфигурации."""
    admin_ids = get_admin_ids()
    user_data = await state.get_data()
    client_name = user_data["client_name"]
    vpn_type = user_data["vpn_type"]
    client_mode = user_data.get("client_mode", False)
    
    if callback.data == "back_to_client_menu":
        mapped_client = get_client_name_for_user(callback.from_user.id)
        if not mapped_client:
            await callback.answer("Доступ запрещен!", show_alert=True)
            await state.clear()
            return
        await callback.message.edit_text(
            f'Ваш клиент: "{mapped_client}". Выберите протокол:',
            reply_markup=create_client_menu(mapped_client),
        )
        await state.clear()
        await callback.answer()
        return
    
    if callback.data == "back_to_client_list":
        if client_mode:
            mapped_client = get_client_name_for_user(callback.from_user.id)
            if not mapped_client:
                await callback.answer("Доступ запрещен!", show_alert=True)
                await state.clear()
                return
            await callback.message.edit_text(
                f'Ваш клиент: "{mapped_client}". Выберите протокол:',
                reply_markup=create_client_menu(mapped_client),
            )
            await state.clear()
            await callback.answer()
            return
        
        clients = await get_clients(vpn_type)
        total_pages = (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        
        await callback.message.edit_text(
            "Список клиентов:",
            reply_markup=create_client_list_keyboard(clients, 1, total_pages, vpn_type, "list"),
        )
        await state.set_state(VPNSetup.list_for_delete)
        await callback.answer()
        return
    
    if callback.data.startswith("openvpn_config_"):
        _, _, interface, _ = callback.data.split("_", 3)
        await state.update_data(interface=interface)
        await callback.message.edit_text(
            f"OpenVPN ({interface}): выберите протокол:",
            reply_markup=create_openvpn_protocol_menu(interface, client_name),
        )
        await state.set_state(VPNSetup.choosing_protocol)
    else:
        _, _, interface, _ = callback.data.split("_", 3)
        await state.update_data(interface=interface)
        await callback.message.edit_text(
            f"WireGuard ({interface}): выберите тип:",
            reply_markup=create_wireguard_type_menu(interface, client_name),
        )
        await state.set_state(VPNSetup.choosing_wg_type)
    
    await callback.answer()


@router.callback_query(VPNSetup.choosing_protocol)
async def handle_protocol_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора протокола OpenVPN."""
    admin_ids = get_admin_ids()
    user_data = await state.get_data()
    client_name = user_data["client_name"]
    
    if callback.from_user.id not in admin_ids:
        allowed_client = get_client_name_for_user(callback.from_user.id)
        if not allowed_client or allowed_client != client_name:
            await callback.answer("Доступ запрещен!", show_alert=True)
            await state.clear()
            return
    
    if callback.data.startswith("send_ovpn_"):
        _, _, interface, proto, _ = callback.data.split("_", 4)
        name_core = client_name.replace("antizapret-", "").replace("vpn-", "")
        
        if proto == "default":
            dir_path = f"/root/antizapret/client/openvpn/{interface}/"
            pattern = re.compile(rf"{interface}-{re.escape(name_core)}-\([^)]+\)\.ovpn")
        else:
            dir_path = f"/root/antizapret/client/openvpn/{interface}-{proto}/"
            pattern = re.compile(rf"{interface}-{re.escape(name_core)}-\([^)]+\)-{proto}\.ovpn")
        
        matched_file = None
        if os.path.exists(dir_path):
            for file in os.listdir(dir_path):
                if pattern.fullmatch(file):
                    matched_file = os.path.join(dir_path, file)
                    break
        
        if matched_file:
            bot = await _get_bot()
            await bot.send_document(
                callback.from_user.id,
                document=FSInputFile(matched_file),
                caption=f"🔐 {os.path.basename(matched_file)}"
            )
            await callback.message.delete()
            
            if callback.from_user.id in admin_ids:
                server_ip = _get_server_ip()
                await callback.message.answer("Главное меню:", reply_markup=create_main_menu(server_ip))
            else:
                from .common import show_client_menu
                await show_client_menu(callback.message, callback.from_user.id)
            await state.clear()
        else:
            await callback.answer("❌ Файл не найден", show_alert=True)
    
    elif callback.data.startswith("back_to_interface_"):
        await _handle_back_to_interface(callback, state)


@router.callback_query(VPNSetup.choosing_wg_type)
async def handle_wg_type_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора типа WireGuard."""
    admin_ids = get_admin_ids()
    user_data = await state.get_data()
    client_name = user_data["client_name"]
    
    if callback.from_user.id not in admin_ids:
        allowed_client = get_client_name_for_user(callback.from_user.id)
        if not allowed_client or allowed_client != client_name:
            await callback.answer("Доступ запрещен!", show_alert=True)
            await state.clear()
            return
    
    if callback.data.startswith("back_to_interface_"):
        await _handle_back_to_interface(callback, state)
        await callback.answer()
        return
    
    if callback.data.startswith("send_wg_"):
        _, _, interface, wg_type, _ = callback.data.split("_", 4)
        
        name_core = client_name.replace("antizapret-", "").replace("vpn-", "")
        dir_path = f"/root/antizapret/client/{'wireguard' if wg_type == 'wg' else 'amneziawg'}/{interface}/"
        pattern = re.compile(rf"{interface}-{re.escape(name_core)}-\([^)]+\)-{wg_type}\.conf")
        
        matched_file = None
        if os.path.exists(dir_path):
            for file in os.listdir(dir_path):
                if pattern.fullmatch(file):
                    matched_file = os.path.join(dir_path, file)
                    break
        
        if not matched_file:
            await callback.answer("❌ Файл конфигурации не найден", show_alert=True)
            await state.clear()
            return
        
        await state.update_data({
            "file_path": matched_file,
            "original_name": os.path.basename(matched_file),
            "short_name": f"{name_core}-{wg_type}.conf",
        })
        
        await callback.message.edit_text(
            "Android может не принимать файлы с длинными именами.\nХотите переименовать файл при отправке?",
            reply_markup=create_rename_confirmation_keyboard(),
        )
        await state.set_state(VPNSetup.confirming_rename)


@router.callback_query(VPNSetup.confirming_rename)
async def handle_rename_confirmation(callback: types.CallbackQuery, state: FSMContext):
    """Обработка подтверждения переименования файла WireGuard."""
    admin_ids = get_admin_ids()
    user_data = await state.get_data()
    file_path = user_data["file_path"]
    
    if not os.path.exists(file_path):
        await callback.answer("❌ Файл не найден", show_alert=True)
        await state.clear()
        return
    
    file_size = os.path.getsize(file_path)
    if file_size == 0:
        await callback.answer("❌ Файл пуст", show_alert=True)
        await state.clear()
        return
    
    if file_size > 50 * 1024 * 1024:
        await callback.answer("❌ Файл слишком большой для отправки в Telegram", show_alert=True)
        await state.clear()
        return
    
    try:
        bot = await _get_bot()
        
        if callback.data == "confirm_rename":
            file = FSInputFile(file_path, filename=user_data["short_name"])
            caption = f"🔐 {user_data['short_name']}"
        else:
            file = FSInputFile(file_path)
            caption = f"🔐 {user_data['original_name']}"
        
        await bot.send_document(chat_id=callback.from_user.id, document=file, caption=caption)
        
        await callback.message.delete()
        if callback.from_user.id in admin_ids:
            server_ip = _get_server_ip()
            await callback.message.answer("Главное меню:", reply_markup=create_main_menu(server_ip))
        else:
            from .common import show_client_menu
            await show_client_menu(callback.message, callback.from_user.id)
    
    except Exception as e:
        print(f"Ошибка при отправке файла: {e}")
        await callback.answer("❌ Ошибка при отправке файла", show_alert=True)
    
    await state.clear()


async def _handle_back_to_interface(callback: types.CallbackQuery, state: FSMContext):
    """Вернуться к выбору интерфейса."""
    user_data = await state.get_data()
    client_name = user_data["client_name"]
    vpn_type = user_data["vpn_type"]
    back_callback = "back_to_client_menu" if user_data.get("client_mode") else "back_to_client_list"
    
    if vpn_type == "openvpn":
        await callback.message.edit_text(
            "Выберите тип конфигурации OpenVPN:",
            reply_markup=create_openvpn_config_menu(client_name, back_callback),
        )
        await state.set_state(VPNSetup.choosing_config_type)
    else:
        await callback.message.edit_text(
            "Выберите тип конфигурации WireGuard:",
            reply_markup=create_wireguard_config_menu(client_name, back_callback),
        )
        await state.set_state(VPNSetup.choosing_config_type)
    
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("cancel_config_"))
async def handle_config_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Обработка отмены выбора конфигурации."""
    user_data = await state.get_data()
    vpn_type = user_data["vpn_type"]
    
    clients = await get_clients(vpn_type)
    total_pages = (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    await callback.message.edit_text(
        "Список клиентов:",
        reply_markup=create_client_list_keyboard(clients, 1, total_pages, vpn_type, "list"),
    )
    await state.clear()
    await callback.answer()


@router.message(VPNSetup.entering_client_name)
async def handle_client_name(message: types.Message, state: FSMContext):
    """Обработка ввода имени клиента при создании."""
    admin_ids = get_admin_ids()
    update_admin_info(message.from_user)
    client_name = message.text.strip()
    
    if not re.match(r"^[a-zA-Z0-9_-]{1,32}$", client_name):
        await message.answer("❌ Некорректное имя! Используйте буквы, цифры, _ и -")
        return
    
    data = await state.get_data()
    option = data["action"]
    
    if option == "1":
        await state.update_data(client_name=client_name)
        await message.answer("Введите количество дней (1-3650):")
        await state.set_state(VPNSetup.entering_days)
    else:
        result = await execute_script(option, client_name)
        if result["returncode"] == 0:
            await _send_config(message.chat.id, client_name, option)
            await message.answer("✅ Клиент создан!")
            server_ip = _get_server_ip()
            await message.answer("Главное меню:", reply_markup=create_main_menu(server_ip))
            vpn_type = "wireguard" if option == "4" else "openvpn"
            log_action("bot", message.from_user.id, message.from_user.full_name, "client_create", f"{client_name} ({vpn_type})")
            await notify_admins(message.from_user.id, message.from_user.full_name, f"создал клиента <b>{client_name}</b> ({vpn_type})")
        else:
            await message.answer(f"❌ Ошибка: {result['stderr']}")
        await state.clear()


@router.message(VPNSetup.entering_days)
async def handle_days(message: types.Message, state: FSMContext):
    """Обработка ввода количества дней при создании клиента OpenVPN."""
    admin_ids = get_admin_ids()
    update_admin_info(message.from_user)
    days = message.text.strip()
    
    if not days.isdigit() or not (1 <= int(days) <= 3650):
        await message.answer("❌ Введите число от 1 до 3650")
        return
    
    data = await state.get_data()
    client_name = data["client_name"]
    result = await execute_script("1", client_name, days)
    
    if result["returncode"] == 0:
        await _send_config(message.chat.id, client_name, "1")
        server_ip = _get_server_ip()
        await message.answer("✅ Клиент создан!", reply_markup=create_main_menu(server_ip))
        log_action("bot", message.from_user.id, message.from_user.full_name, "client_create", f"{client_name} (openvpn)")
        await notify_admins(message.from_user.id, message.from_user.full_name, f"создал клиента <b>{client_name}</b> (openvpn)")
    else:
        await message.answer(f"❌ Ошибка: {result['stderr']}")
    await state.clear()


@router.message(VPNSetup.deleting_client)
async def handle_delete_client(message: types.Message, state: FSMContext):
    """Обработка ввода при удалении клиента."""
    update_admin_info(message.from_user)
    client_name = message.text.strip()
    data = await state.get_data()
    vpn_type = "openvpn" if data["action"] == "2" else "wireguard"
    
    await message.answer(
        f"Вы уверены, что хотите удалить клиента {client_name}?",
        reply_markup=create_confirmation_keyboard(client_name, vpn_type),
    )
    await state.clear()


async def _send_config(chat_id: int, client_name: str, option: str):
    """Отправить файлы конфигурации пользователю."""
    bot = await _get_bot()
    
    try:
        if option == "4":
            name_core = client_name.replace("antizapret-", "").replace("vpn-", "")
            directories = [
                ("/root/antizapret/client/amneziawg/antizapret", "AmneziaWG (antizapret)"),
                ("/root/antizapret/client/amneziawg/vpn", "AmneziaWG (vpn)"),
            ]
            pattern = re.compile(rf"(antizapret|vpn)-{re.escape(name_core)}-\([^)]+\)-am\.conf")
        else:
            directories = [
                ("/root/antizapret/client/openvpn/antizapret", "OpenVPN (antizapret)"),
                ("/root/antizapret/client/openvpn/vpn", "OpenVPN (vpn)"),
            ]
            pattern = re.compile(rf"(antizapret|vpn)-{re.escape(client_name)}-\([^)]+\)\.ovpn")
        
        timeout = 25
        interval = 0.5
        files_found = []
        
        for directory, config_type in directories:
            try:
                for filename in os.listdir(directory):
                    if pattern.fullmatch(filename):
                        full_path = os.path.join(directory, filename)
                        
                        elapsed = 0
                        while not os.path.exists(full_path) and elapsed < timeout:
                            await asyncio.sleep(interval)
                            elapsed += interval
                        
                        if os.path.exists(full_path):
                            files_found.append((full_path, config_type))
                        break
            except FileNotFoundError:
                continue
        
        for path, config_type in files_found:
            await bot.send_document(
                chat_id,
                document=FSInputFile(path),
                caption=f'🔐 Клиент "{client_name}". {config_type}.',
            )
        
        if not files_found:
            await bot.send_message(chat_id, "❌ Файлы конфигураций не найдены")
    
    except Exception as e:
        print(f"Ошибка: {e}")
        await bot.send_message(chat_id, "⚠️ Ошибка при отправке конфигурации")
