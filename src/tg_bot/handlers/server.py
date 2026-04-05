"""Обработчики управления сервером."""

import asyncio

from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from ..config import get_admin_ids, set_load_thresholds
from ..keyboards import (
    create_server_menu,
    create_thresholds_menu,
    create_reboot_confirm_menu,
    create_back_keyboard,
)
from ..states import VPNSetup
from ..server import (
    get_server_stats,
    get_services_status_text,
    get_online_clients_text,
    VPN_MONITORED_SERVICES,
)
from ..bot import cancel_pending_vpn_restart, vpn_run_restart_now
from ..audit import log_action, notify_admins

router = Router()


@router.callback_query(lambda c: c.data == "server_stats")
async def handle_server_stats(callback: types.CallbackQuery):
    """Обработка запроса статистики сервера."""
    admin_ids = get_admin_ids()
    
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    
    stats_text = await get_server_stats()
    await callback.message.edit_text(
        stats_text,
        reply_markup=create_back_keyboard("server_menu"),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "server_reboot")
async def handle_server_reboot(callback: types.CallbackQuery):
    """Обработка запроса перезагрузки сервера."""
    admin_ids = get_admin_ids()
    
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "⚠️ <b>Внимание!</b>\n\n"
        "Перезагрузка сервера прервет активные подключения. "
        "Подтвердите действие.",
        reply_markup=create_reboot_confirm_menu(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "server_reboot_confirm")
async def handle_server_reboot_confirm(callback: types.CallbackQuery):
    """Обработка подтверждения перезагрузки сервера."""
    admin_ids = get_admin_ids()
    
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    
    await callback.message.edit_text("⏳ Перезагрузка сервера...")
    log_action("bot", callback.from_user.id, callback.from_user.full_name, "server_reboot", "")
    await notify_admins(callback.from_user.id, callback.from_user.full_name, "перезагрузил сервер")
    try:
        await asyncio.create_subprocess_exec("/sbin/shutdown", "-r", "now")
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка запуска перезагрузки:\n{e}",
            reply_markup=create_server_menu(),
        )
        return
    
    await callback.answer("")


@router.callback_query(lambda c: c.data and c.data.startswith("vpn_ar_now_"))
async def handle_vpn_autorestart_now(callback: types.CallbackQuery):
    """Немедленный перезапуск VPN-службы (отменяет отложенный таймер)."""
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    try:
        idx = int(callback.data.rsplit("_", 1)[-1])
    except ValueError:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    if not (0 <= idx < len(VPN_MONITORED_SERVICES)):
        await callback.answer("Неизвестная служба", show_alert=True)
        return
    label, unit = VPN_MONITORED_SERVICES[idx]
    ok = await vpn_run_restart_now(unit, label)
    await callback.answer("Перезапуск выполнен" if ok else "Перезапуск не дал active", show_alert=not ok)


@router.callback_query(lambda c: c.data and c.data.startswith("vpn_ar_cancel_"))
async def handle_vpn_autorestart_cancel(callback: types.CallbackQuery):
    """Отмена автоперезапуска VPN-службы до истечения 30 с."""
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    try:
        idx = int(callback.data.rsplit("_", 1)[-1])
    except ValueError:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    if not (0 <= idx < len(VPN_MONITORED_SERVICES)):
        await callback.answer("Неизвестная служба", show_alert=True)
        return
    unit = VPN_MONITORED_SERVICES[idx][1]
    if cancel_pending_vpn_restart(unit):
        await callback.answer("Автоперезапуск отменён")
    else:
        await callback.answer("Таймер уже истёк или перезапуск выполнен")


@router.callback_query(lambda c: c.data == "server_services")
async def handle_server_services(callback: types.CallbackQuery):
    """Обработка запроса статуса служб сервера."""
    admin_ids = get_admin_ids()
    
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    
    services_text = await get_services_status_text()
    await callback.message.edit_text(
        services_text,
        reply_markup=create_back_keyboard("server_menu"),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "server_online")
async def handle_server_online(callback: types.CallbackQuery):
    """Обработка запроса списка онлайн-клиентов."""
    admin_ids = get_admin_ids()
    
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    
    online_text = await get_online_clients_text()
    await callback.message.edit_text(
        online_text,
        reply_markup=create_back_keyboard("server_menu"),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "server_thresholds")
async def handle_server_thresholds(callback: types.CallbackQuery):
    """Обработка меню порогов нагрузки."""
    admin_ids = get_admin_ids()
    
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "Пороги нагрузки:", reply_markup=create_thresholds_menu()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data in ["set_cpu_threshold", "set_memory_threshold"])
async def handle_set_threshold_prompt(callback: types.CallbackQuery, state: FSMContext):
    """Обработка запросов на ввод порогов."""
    admin_ids = get_admin_ids()
    
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    
    if callback.data == "set_cpu_threshold":
        await callback.message.edit_text(
            "Введите порог CPU (1-100):",
            reply_markup=create_back_keyboard("server_thresholds"),
        )
        await state.set_state(VPNSetup.entering_cpu_threshold)
    else:
        await callback.message.edit_text(
            "Введите порог RAM (1-100):",
            reply_markup=create_back_keyboard("server_thresholds"),
        )
        await state.set_state(VPNSetup.entering_memory_threshold)
    
    await callback.answer()


@router.message(VPNSetup.entering_cpu_threshold)
async def handle_cpu_threshold_input(message: types.Message, state: FSMContext):
    """Обработка ввода порога CPU."""
    admin_ids = get_admin_ids()
    
    if message.from_user.id not in admin_ids:
        await message.answer("Доступ запрещен")
        await state.clear()
        return
    
    value = message.text.strip()
    if not value.isdigit() or not (1 <= int(value) <= 100):
        await message.answer("Введите число от 1 до 100.")
        return
    
    set_load_thresholds(cpu_threshold=int(value))
    await message.answer("Порог CPU обновлен.", reply_markup=create_server_menu())
    await state.clear()


@router.message(VPNSetup.entering_memory_threshold)
async def handle_memory_threshold_input(message: types.Message, state: FSMContext):
    """Обработка ввода порога памяти."""
    admin_ids = get_admin_ids()
    
    if message.from_user.id not in admin_ids:
        await message.answer("Доступ запрещен")
        await state.clear()
        return
    
    value = message.text.strip()
    if not value.isdigit() or not (1 <= int(value) <= 100):
        await message.answer("Введите число от 1 до 100.")
        return
    
    set_load_thresholds(memory_threshold=int(value))
    await message.answer("Порог RAM обновлен.", reply_markup=create_server_menu())
    await state.clear()
