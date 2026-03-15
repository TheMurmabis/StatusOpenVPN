"""Обработчики колбэков администратора для управления VPN."""

import os
import re

from aiogram import Router, types
from aiogram.types import FSInputFile
from aiogram.fsm.context import FSMContext

from ..config import get_admin_ids, ITEMS_PER_PAGE, set_client_mapping
from ..keyboards import (
    create_main_menu,
    create_client_list_keyboard,
    create_confirmation_keyboard,
    create_request_actions_keyboard,
    create_request_client_list_keyboard,
)
from ..states import VPNSetup
from ..utils import (
    execute_script,
    get_clients,
    get_all_clients_unique,
    cleanup_openvpn_files,
    get_external_ip,
)
from ..audit import log_action, notify_admins

router = Router()


def _get_server_ip():
    return get_external_ip()


async def _get_bot():
    """Получить экземпляр бота (ленивая инициализация)."""
    from ..bot import get_bot
    return get_bot()


@router.callback_query(lambda c: c.from_user.id in get_admin_ids())
async def handle_callback_query(callback: types.CallbackQuery, state: FSMContext):
    """Обработка колбэк-запросов администратора."""
    data = callback.data
    admin_ids = get_admin_ids()
    
    try:
        # Запрос доступа: Отклонить (req_no_<uid>)
        if data.startswith("req_no_"):
            parts = data.split("_", 2)
            uid = parts[2] if len(parts) > 2 else ""
            if uid.isdigit():
                bot = await _get_bot()
                try:
                    await bot.send_message(
                        int(uid),
                        "❌ Ваш запрос доступа отклонён администратором.",
                    )
                except Exception:
                    pass
                await callback.message.edit_text(f"❌ Запрос от <code>{uid}</code> отклонён.")
                log_action("bot", callback.from_user.id, callback.from_user.full_name, "request_reject", f"{uid}(отклонён)")
            await callback.answer()
            return

        # Запрос доступа: Подтвердить с именем — переходим в FSM ввода имени (req_custom_<uid>)
        if data.startswith("req_custom_"):
            uid = data.split("_", 2)[2]
            if uid.isdigit():
                await state.update_data(request_user_id=int(uid))
                await state.set_state(VPNSetup.entering_request_client_name)
                await callback.message.edit_text(
                    f"Введите имя клиента для ID <code>{uid}</code>:"
                )
            await callback.answer()
            return

        # Запрос доступа: Выбрать клиента из списка (req_pick_<uid>_<suggested>)
        if data.startswith("req_pick_"):
            parts = data.split("_", 3)
            uid = parts[2] if len(parts) > 2 else ""
            suggested = parts[3] if len(parts) > 3 else f"user_{uid}"
            if uid.isdigit():
                clients = await get_all_clients_unique()
                if not clients:
                    await callback.message.edit_text(
                        f"❌ Нет ни одного клиента (OpenVPN/WireGuard). "
                        f"Используйте «Ввести имя» для ID <code>{uid}</code>."
                    )
                    await callback.answer()
                    return
                total_pages = max(1, (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
                await callback.message.edit_text(
                    f"📋 Запрос от <code>{uid}</code>. Выберите клиента для привязки:",
                    reply_markup=create_request_client_list_keyboard(
                        uid, clients, 1, total_pages, suggested
                    ),
                )
            await callback.answer()
            return

        # Запрос доступа: пагинация списка клиентов (req_list_<uid>_<page>)
        if data.startswith("req_list_"):
            parts = data.split("_", 3)
            uid = parts[2] if len(parts) > 2 else ""
            try:
                page = int(parts[3]) if len(parts) > 3 else 1
            except ValueError:
                page = 1
            if uid.isdigit():
                clients = await get_all_clients_unique()
                total_pages = max(1, (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
                page = max(1, min(page, total_pages))
                suggested = f"user_{uid}"
                await callback.message.edit_text(
                    f"📋 Запрос от <code>{uid}</code>. Выберите клиента для привязки:",
                    reply_markup=create_request_client_list_keyboard(
                        uid, clients, page, total_pages, suggested
                    ),
                )
            await callback.answer()
            return

        # Запрос доступа: привязать выбранного клиента (req_bind_<uid>_<client_name>)
        if data.startswith("req_bind_"):
            parts = data.split("_", 3)
            uid = parts[2] if len(parts) > 2 else ""
            client_name = parts[3] if len(parts) > 3 else ""
            if uid.isdigit() and client_name:
                set_client_mapping(uid, client_name)
                bot = await _get_bot()
                try:
                    await bot.send_message(
                        int(uid),
                        "✅ Ваш запрос доступа одобрен. Нажмите /start для входа.",
                    )
                except Exception:
                    pass
                await callback.message.edit_text(
                    f"✅ Запрос от <code>{uid}</code> одобрен. Привязан к клиенту: <b>{client_name}</b>"
                )
                log_action("bot", callback.from_user.id, callback.from_user.full_name, "request_approve", f"{uid}→{client_name}")
            await callback.answer()
            return

        # Запрос доступа: назад к кнопкам запроса (req_back_<uid>_<suggested>)
        if data.startswith("req_back_"):
            parts = data.split("_", 3)
            uid = parts[2] if len(parts) > 2 else ""
            suggested = parts[3] if len(parts) > 3 else f"user_{uid}"
            if uid.isdigit():
                await callback.message.edit_text(
                    f"Клиент: —\nID: <code>{uid}</code>\n\n"
                    "Выберите клиента, введите имя клиента или отклоните запрос.",
                    reply_markup=create_request_actions_keyboard(int(uid), suggested),
                )
            await callback.answer()
            return

        # Pagination
        if data.startswith("page_"):
            _, action, vpn_type, page = data.split("_", 3)
            page = int(page)
            clients = await get_clients(vpn_type)
            total_pages = (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
            await callback.message.edit_text(
                "Список клиентов:",
                reply_markup=create_client_list_keyboard(clients, page, total_pages, vpn_type, action),
            )
            await callback.answer()
            return
        
        # Delete handling
        if data.startswith("delete_"):
            _, vpn_type, client_name = data.split("_", 2)
            await callback.message.edit_text(
                f"❓ Удалить клиента {client_name} ({vpn_type})?",
                reply_markup=create_confirmation_keyboard(client_name, vpn_type),
            )
            await callback.answer()
            return
        
        # Initialize deletion list
        if data in ["2", "5"]:
            vpn_type = "openvpn" if data == "2" else "wireguard"
            clients = await get_clients(vpn_type)
            
            if not clients:
                await callback.message.edit_text("❌ Нет клиентов для удаления")
                return
            
            total_pages = (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
            await callback.message.edit_text(
                "Выберите клиента для удаления:",
                reply_markup=create_client_list_keyboard(clients, 1, total_pages, vpn_type, "delete"),
            )
            await state.set_state(VPNSetup.list_for_delete)
            await callback.answer()
            return
        
        # Confirm deletion
        if data.startswith("confirm_"):
            _, vpn_type, client_name = data.split("_", 2)
            option = "2" if vpn_type == "openvpn" else "5"
            
            try:
                result = await execute_script(option, client_name)
                
                if vpn_type == "openvpn" and result["returncode"] == 0:
                    deleted_files = await cleanup_openvpn_files(client_name)
                    if deleted_files:
                        result["additional_deleted"] = deleted_files
                
                if result["returncode"] == 0:
                    msg = f"✅ Клиент {client_name} удален!"
                    if vpn_type == "openvpn" and result.get("additional_deleted"):
                        msg += f"\nДополнительно удалено файлов: {len(result['additional_deleted'])}"
                    
                    await callback.message.edit_text(msg)
                    server_ip = _get_server_ip()
                    await callback.message.answer("Главное меню:", reply_markup=create_main_menu(server_ip))
                    log_action("bot", callback.from_user.id, callback.from_user.full_name, "client_delete", f"{client_name} ({vpn_type})")
                    await notify_admins(callback.from_user.id, callback.from_user.full_name, f"удалил клиента <b>{client_name}</b> ({vpn_type})")
                else:
                    await callback.message.edit_text(f"❌ Ошибка: {result['stderr']}")
            
            except Exception as e:
                print(f"Ошибка при удалении клиента: {e}")
            
            finally:
                await callback.answer()
                await state.clear()
            return
        
        if data == "cancel_delete":
            server_ip = _get_server_ip()
            await callback.message.edit_text("❌ Удаление отменено", reply_markup=create_main_menu(server_ip))
            await callback.answer()
            return
        
        # Client list
        if data in ["3", "6"]:
            vpn_type = "openvpn" if data == "3" else "wireguard"
            clients = await get_clients(vpn_type)
            total_pages = (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
            await callback.message.edit_text(
                "Список клиентов:",
                reply_markup=create_client_list_keyboard(clients, 1, total_pages, vpn_type, "list"),
            )
            await callback.answer()
            return
        
        # Create client
        if data in ["1", "4"]:
            await state.update_data(action=data)
            await callback.message.edit_text("Введите имя нового клиента:")
            await state.set_state(VPNSetup.entering_client_name)
            await callback.answer()
            return
        
        # Recreate files
        if data == "7":
            await callback.message.edit_text("⏳ Идет пересоздание файлов...")
            result = await execute_script("7")
            if result["returncode"] == 0:
                await callback.message.edit_text("✅ Файлы успешно пересозданы!")
                server_ip = _get_server_ip()
                await callback.message.answer("Главное меню:", reply_markup=create_main_menu(server_ip))
                log_action("bot", callback.from_user.id, callback.from_user.full_name, "files_recreate", "")
                await notify_admins(callback.from_user.id, callback.from_user.full_name, "пересоздал файлы клиентов")
            else:
                await callback.message.edit_text(f"❌ Ошибка: {result['stderr']}")
            await callback.answer()
            return
        
        # Create backup
        if data == "8":
            await callback.message.edit_text("⏳ Создаю бэкап...")
            result = await execute_script("8")
            
            if result["returncode"] == 0:
                if await _send_backup(callback.from_user.id):
                    await callback.message.delete()
                    server_ip = _get_server_ip()
                    await callback.message.answer("Главное меню:", reply_markup=create_main_menu(server_ip))
                else:
                    await callback.message.edit_text("❌ Не удалось отправить бэкап")
            else:
                await callback.message.edit_text(f"❌ Ошибка при создании бэкапа: {result['stderr']}")
            
            await callback.answer()
            return
    
    except Exception as e:
        print(f"Error: {e}")
        await callback.answer("⚠️ Произошла ошибка!")


@router.message(VPNSetup.entering_request_client_name)
async def handle_request_client_name_input(message: types.Message, state: FSMContext):
    """Обработка ввода имени клиента при одобрении запроса доступа."""
    if message.from_user.id not in get_admin_ids():
        await state.clear()
        return
    payload = (message.text or "").strip()
    match = re.match(r"^([a-zA-Z0-9_-]{1,32})$", payload)
    if not match:
        await message.answer(
            "❌ Некорректное имя. Используйте только латиницу, цифры, _ и - (до 32 символов)."
        )
        return
    client_name = match.group(1)
    data = await state.get_data()
    uid = data.get("request_user_id")
    await state.clear()
    if not uid:
        await message.answer("Сессия истекла. Попросите пользователя отправить запрос снова.")
        return
    uid_str = str(uid)
    set_client_mapping(uid_str, client_name)
    bot = await _get_bot()
    try:
        await bot.send_message(
            uid,
            "✅ Ваш запрос доступа одобрен. Нажмите /start для входа.",
        )
    except Exception:
        pass
    server_ip = _get_server_ip()
    await message.answer(
        f"✅ Запрос от <code>{uid_str}</code> одобрен. Имя клиента: <b>{client_name}</b>",
        reply_markup=create_main_menu(server_ip),
    )
    log_action("bot", message.from_user.id, message.from_user.full_name, "request_approve", f"{uid}→{client_name}")


async def _send_backup(chat_id: int) -> bool:
    """Отправить файл бэкапа пользователю."""
    bot = await _get_bot()
    server_ip = _get_server_ip()
    
    paths_to_check = [
        f"/root/antizapret/backup-{server_ip}.tar.gz",
        "/root/antizapret/backup.tar.gz",
    ]
    
    for backup_path in paths_to_check:
        try:
            if os.path.exists(backup_path):
                await bot.send_document(
                    chat_id=chat_id,
                    document=FSInputFile(backup_path),
                    caption="📦 Бэкап клиентов",
                )
                return True
        except Exception as e:
            print(f"Ошибка отправки бэкапа ({backup_path}): {e}")
            return False
    
    return False
