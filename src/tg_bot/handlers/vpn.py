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
    create_openvpn_protocol_menu_filtered,
    create_wireguard_type_menu,
    create_wireguard_type_menu_filtered,
    create_client_list_keyboard,
    create_confirmation_keyboard,
    create_rename_confirmation_keyboard,
)
from ..states import VPNSetup
from ..utils import execute_script, get_clients, cleanup_openvpn_files, get_external_ip
from ..audit import log_action, notify_admins
from ..client_status_service import get_client_statuses

router = Router()


def _get_server_ip():
    return get_external_ip()


async def _get_bot():
    """Получить экземпляр бота (ленивая инициализация)."""
    from ..bot import get_bot
    return get_bot()


def _get_allowed_openvpn_protocols(protocols: dict) -> list[str]:
    default_allowed = protocols.get("openvpn_default", True)
    allowed = []
    for proto in ("default", "tcp", "udp"):
        if proto == "default":
            if default_allowed:
                allowed.append(proto)
        elif protocols.get(f"openvpn_{proto}", True):
            allowed.append(proto)
    return allowed


def _get_allowed_wireguard_types(protocols: dict) -> list[str]:
    return [
        wg_type
        for wg_type in ("wg", "am")
        if protocols.get(f"wireguard_{wg_type}", True)
    ]


def _build_openvpn_file_info(interface: str, client_name: str, proto: str):
    name_core = client_name.replace("antizapret-", "").replace("vpn-", "")
    if proto == "default":
        dir_path = f"/root/antizapret/client/openvpn/{interface}/"
        pattern = re.compile(rf"{interface}-{re.escape(name_core)}-\([^)]+\)\.ovpn")
    else:
        dir_path = f"/root/antizapret/client/openvpn/{interface}-{proto}/"
        pattern = re.compile(rf"{interface}-{re.escape(name_core)}-\([^)]+\)-{proto}\.ovpn")
    return dir_path, pattern


def _find_file_in_dir(dir_path: str, pattern: re.Pattern):
    if not os.path.exists(dir_path):
        return None
    for file in os.listdir(dir_path):
        if pattern.fullmatch(file):
            return os.path.join(dir_path, file)
    return None


async def _send_openvpn_config(callback: types.CallbackQuery, state: FSMContext, client_name: str, interface: str, proto: str):
    admin_ids = get_admin_ids()
    dir_path, pattern = _build_openvpn_file_info(interface, client_name, proto)
    matched_file = _find_file_in_dir(dir_path, pattern)

    if not matched_file:
        await callback.answer("❌ Файл не найден", show_alert=True)
        return False

    bot = await _get_bot()
    await bot.send_document(
        callback.from_user.id,
        document=FSInputFile(matched_file),
        caption=f"🔐 {os.path.basename(matched_file)}",
    )
    await callback.message.delete()

    if callback.from_user.id in admin_ids:
        server_ip = _get_server_ip()
        await callback.message.answer("Главное меню:", reply_markup=create_main_menu(server_ip))
    else:
        from .common import show_client_menu
        await show_client_menu(callback.message, callback.from_user.id)
    await state.clear()
    return True


async def _process_wg_selection(
    callback: types.CallbackQuery,
    state: FSMContext,
    client_name: str,
    interface: str,
    wg_type: str,
):
    admin_ids = get_admin_ids()
    name_core = client_name.replace("antizapret-", "").replace("vpn-", "")
    name_core = name_core.replace(" ", "_")
    dir_path = f"/root/antizapret/client/{'wireguard' if wg_type == 'wg' else 'amneziawg'}/{interface}/"
    pattern = re.compile(rf"{interface}-{re.escape(name_core)}-\([^)]+\)-{wg_type}\.conf")

    matched_file = _find_file_in_dir(dir_path, pattern)
    if not matched_file:
        await callback.answer("❌ Файл конфигурации не найден", show_alert=True)
        await state.clear()
        return

    from ..config import load_settings as load_bot_settings
    try:
        main_settings = load_bot_settings()
        shorten_filenames = bool(main_settings.get("shorten_wg_filenames", False))
    except Exception:
        shorten_filenames = False

    short_name = f"{interface}-{name_core}-{wg_type}.conf"
    await state.update_data(
        {
            "file_path": matched_file,
            "original_name": os.path.basename(matched_file),
            "short_name": short_name,
            "shorten_filenames": shorten_filenames,
        }
    )

    if shorten_filenames:
        file_size = os.path.getsize(matched_file)
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
            file = FSInputFile(matched_file, filename=short_name)
            await bot.send_document(
                chat_id=callback.from_user.id,
                document=file,
                caption=f"🔐 {short_name}",
            )
            await callback.message.delete()
            if callback.from_user.id in admin_ids:
                server_ip = _get_server_ip()
                await callback.message.answer(
                    "Главное меню:", reply_markup=create_main_menu(server_ip)
                )
            else:
                from .common import show_client_menu
                await show_client_menu(callback.message, callback.from_user.id)
        except Exception as e:
            print(f"Ошибка при отправке файла: {e}")
            await callback.answer("❌ Ошибка при отправке файла", show_alert=True)

        await state.clear()
        await callback.answer()
        return

    await callback.message.edit_text(
        "Некоторые приложения не принимают файлы с длинными именами.\nХотите использовать короткое имя файла?",
        reply_markup=create_rename_confirmation_keyboard(),
    )
    await state.set_state(VPNSetup.confirming_rename)


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

        # Проверка доступных протоколов для клиента
        from ..config import get_client_allowed_protocols
        protocols = get_client_allowed_protocols(str(callback.from_user.id))

        if vpn_type == "openvpn" and not protocols.get("openvpn", True):
            await callback.answer("OpenVPN недоступен для вас. Обратитесь к администратору.", show_alert=True)
            return

        if vpn_type == "wireguard" and not protocols.get("wireguard", True):
            await callback.answer("WireGuard недоступен для вас. Обратитесь к администратору.", show_alert=True)
            return

        if vpn_type == "openvpn":
            openvpn_interfaces = []
            if protocols.get("openvpn_vpn", True):
                openvpn_interfaces.append("vpn")
            if protocols.get("openvpn_antizapret", True):
                openvpn_interfaces.append("antizapret")
            openvpn_protocols = _get_allowed_openvpn_protocols(protocols)
            openvpn_combinations = [
                (interface, proto)
                for interface in openvpn_interfaces
                for proto in openvpn_protocols
            ]
            if len(openvpn_combinations) == 1:
                await callback.answer()
                interface, proto = openvpn_combinations[0]
                await state.update_data(client_mode=True, client_name=client_name, vpn_type=vpn_type)
                await _send_openvpn_config(callback, state, client_name, interface, proto)
                return

        if vpn_type == "wireguard":
            wireguard_interfaces = []
            if protocols.get("wireguard_vpn", True):
                wireguard_interfaces.append("vpn")
            if protocols.get("wireguard_antizapret", True):
                wireguard_interfaces.append("antizapret")
            wireguard_types = _get_allowed_wireguard_types(protocols)
            wireguard_combinations = [
                (interface, wg_type)
                for interface in wireguard_interfaces
                for wg_type in wireguard_types
            ]
            if len(wireguard_combinations) == 1:
                await callback.answer()
                interface, wg_type = wireguard_combinations[0]
                await state.update_data(client_mode=True, client_name=client_name, vpn_type=vpn_type)
                await _process_wg_selection(callback, state, client_name, interface, wg_type)
                return

        await state.update_data(client_mode=True)

    await state.update_data(client_name=client_name, vpn_type=vpn_type)

    back_callback = (
        "back_to_client_menu"
        if callback.from_user.id not in admin_ids
        else "back_to_client_list"
    )

    # Передаём telegram_id для клиентов, чтобы показывать только доступные конфигурации
    telegram_id = None if callback.from_user.id in admin_ids else callback.from_user.id

    if vpn_type == "openvpn":
        await callback.message.edit_text(
            "Выберите тип конфигурации OpenVPN:",
            reply_markup=create_openvpn_config_menu(client_name, back_callback, telegram_id),
        )
        await state.set_state(VPNSetup.choosing_config_type)
    else:
        await callback.message.edit_text(
            "Выберите тип конфигурации WireGuard:",
            reply_markup=create_wireguard_config_menu(client_name, back_callback, telegram_id),
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
            reply_markup=create_client_menu(mapped_client, callback.from_user.id),
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
                reply_markup=create_client_menu(mapped_client, callback.from_user.id),
            )
            await state.clear()
            await callback.answer()
            return
        
        clients = await get_clients(vpn_type)
        total_pages = (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        statuses = get_client_statuses(vpn_type, clients)
        
        await callback.message.edit_text(
            "Список клиентов:",
            reply_markup=create_client_list_keyboard(
                clients,
                1,
                total_pages,
                vpn_type,
                "list",
                statuses,
            ),
        )
        await state.set_state(VPNSetup.list_for_delete)
        await callback.answer()
        return

    if callback.data.startswith("page_list_"):
        _, _, target_vpn_type, page_raw = callback.data.split("_", 3)
        page = int(page_raw)
        clients = await get_clients(target_vpn_type)
        total_pages = max(1, (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        page = max(1, min(page, total_pages))
        statuses = get_client_statuses(target_vpn_type, clients)
        await callback.message.edit_text(
            "Список клиентов:",
            reply_markup=create_client_list_keyboard(
                clients,
                page,
                total_pages,
                target_vpn_type,
                "list",
                statuses,
            ),
        )
        await state.clear()
        await callback.answer()
        return

    if callback.data.startswith("clist_"):
        _, target_vpn_type, page_raw, target_client_name = callback.data.split("_", 3)
        page = int(page_raw)
        from ..client_status_service import get_client_brief
        from ..keyboards import create_client_actions_keyboard

        brief = get_client_brief(target_vpn_type, target_client_name)
        status = brief.get("status", {})
        stats = brief.get("stats", {})
        state_label = {
            "online": "🟢 онлайн",
            "offline": "🔴 оффлайн",
            "blocked": "🔴🚫 заблокирован",
        }.get(status.get("state", "offline"), "🔴 оффлайн")
        await callback.message.edit_text(
            (
                f"<b>{target_client_name}</b>\n"
                f"Статус: {state_label}\n\n"
                f"<b>Краткая статистика:</b>\n"
                f"⬇️ Сегодня: {stats.get('today_received', '—')}\n"
                f"⬆️ Сегодня: {stats.get('today_sent', '—')}\n"
                f"🕒 Активность: {stats.get('last_activity', '—')}"
            ),
            reply_markup=create_client_actions_keyboard(
                vpn_type=target_vpn_type,
                client_name=target_client_name,
                is_blocked=bool(status.get("blocked", False)),
                list_page=page,
            ),
        )
        await callback.answer()
        return
    
    if callback.data.startswith("openvpn_config_"):
        _, _, interface, _ = callback.data.split("_", 3)
        from ..config import get_client_allowed_protocols
        protocol_settings = (
            get_client_allowed_protocols(str(callback.from_user.id))
            if callback.from_user.id not in admin_ids
            else {
                "openvpn_default": True,
                "openvpn_tcp": True,
                "openvpn_udp": True,
            }
        )
        allowed_openvpn = _get_allowed_openvpn_protocols(protocol_settings)

        # Проверка доступа для клиентов
        if callback.from_user.id not in admin_ids:
            protocols = get_client_allowed_protocols(str(callback.from_user.id))

            if interface == "vpn" and not protocols.get("openvpn_vpn", True):
                await callback.answer("OpenVPN VPN недоступен для вас. Обратитесь к администратору.", show_alert=True)
                await state.clear()
                return
            elif interface == "antizapret" and not protocols.get("openvpn_antizapret", True):
                await callback.answer("OpenVPN Antizapret недоступен для вас. Обратитесь к администратору.", show_alert=True)
                await state.clear()
                return

        if not allowed_openvpn:
            await callback.answer("OpenVPN недоступен: администратор отключил все варианты.", show_alert=True)
            await state.clear()
            return

        await state.update_data(interface=interface)
        if len(allowed_openvpn) == 1:
            await _send_openvpn_config(callback, state, client_name, interface, allowed_openvpn[0])
        else:
            if callback.from_user.id in admin_ids:
                protocol_menu = create_openvpn_protocol_menu(interface, client_name)
            else:
                protocol_menu = create_openvpn_protocol_menu_filtered(interface, client_name, protocol_settings)
            await callback.message.edit_text(
                f"OpenVPN ({interface}): выберите протокол:",
                reply_markup=protocol_menu,
            )
            await state.set_state(VPNSetup.choosing_protocol)
    elif callback.data.startswith("wireguard_config_"):
        _, _, interface, _ = callback.data.split("_", 3)
        from ..config import get_client_allowed_protocols
        protocol_settings = (
            get_client_allowed_protocols(str(callback.from_user.id))
            if callback.from_user.id not in admin_ids
            else {"wireguard_wg": True, "wireguard_am": True}
        )
        allowed_wg_types = _get_allowed_wireguard_types(protocol_settings)

        # Проверка доступа для клиентов
        if callback.from_user.id not in admin_ids:
            protocols = get_client_allowed_protocols(str(callback.from_user.id))

            if interface == "vpn" and not protocols.get("wireguard_vpn", True):
                await callback.answer("WireGuard VPN недоступен для вас. Обратитесь к администратору.", show_alert=True)
                await state.clear()
                return
            elif interface == "antizapret" and not protocols.get("wireguard_antizapret", True):
                await callback.answer("WireGuard Antizapret недоступен для вас. Обратитесь к администратору.", show_alert=True)
                await state.clear()
                return

        if not allowed_wg_types:
            await callback.answer("WireGuard недоступен: администратор отключил все профили.", show_alert=True)
            await state.clear()
            return

        await state.update_data(interface=interface)
        if len(allowed_wg_types) == 1:
            wg_type = allowed_wg_types[0]
            await _process_wg_selection(callback, state, client_name, interface, wg_type)
            return
        if callback.from_user.id in admin_ids:
            wg_type_menu = create_wireguard_type_menu(interface, client_name)
        else:
            wg_type_menu = create_wireguard_type_menu_filtered(interface, client_name, protocol_settings)
        await callback.message.edit_text(
            f"WireGuard ({interface}): выберите тип:",
            reply_markup=wg_type_menu,
        )
        await state.set_state(VPNSetup.choosing_wg_type)
    else:
        await callback.answer()
        return
    
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
        from ..config import get_client_allowed_protocols
        if callback.from_user.id not in admin_ids:
            protocols = get_client_allowed_protocols(str(callback.from_user.id))
            if not protocols.get(f"openvpn_{proto}", True):
                await callback.answer("Этот протокол OpenVPN недоступен для вас.", show_alert=True)
                await state.clear()
                return

        await _send_openvpn_config(callback, state, client_name, interface, proto)
    
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
        from ..config import get_client_allowed_protocols
        if callback.from_user.id not in admin_ids:
            protocols = get_client_allowed_protocols(str(callback.from_user.id))
            if not protocols.get(f"wireguard_{wg_type}", True):
                await callback.answer("Этот профиль WireGuard недоступен для вас.", show_alert=True)
                await state.clear()
                return
        await _process_wg_selection(callback, state, client_name, interface, wg_type)


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
    selected_list_page = user_data.get("selected_list_page")
    if selected_list_page:
        back_callback = f"clist_{vpn_type}_{selected_list_page}_{client_name}"
    else:
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
    statuses = get_client_statuses(vpn_type, clients)
    await callback.message.edit_text(
        "Список клиентов:",
        reply_markup=create_client_list_keyboard(
            clients,
            1,
            total_pages,
            vpn_type,
            "list",
            statuses,
        ),
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
