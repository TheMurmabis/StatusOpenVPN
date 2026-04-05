"""Управление экземпляром бота с ленивой инициализацией."""

import asyncio
import time
import datetime

_bot = None
_dp = None


def get_bot():
    """Получить или создать экземпляр бота (ленивая инициализация)."""
    global _bot
    if _bot is None:
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode
        from .config import get_bot_token
        
        token = get_bot_token()
        _bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    return _bot


def get_dispatcher():
    """Получить или создать экземпляр диспетчера (ленивая инициализация)."""
    global _dp
    if _dp is None:
        from aiogram import Dispatcher
        _dp = Dispatcher()
        _register_handlers(_dp)
    return _dp


def _register_handlers(dp):
    """Зарегистрировать все обработчики в диспетчере."""
    from .handlers import common, menus, server, vpn, admin
    from .middlewares import BannedUserMiddleware, UnlistedUserSilenceMiddleware

    dp.update.outer_middleware(BannedUserMiddleware())
    dp.update.outer_middleware(UnlistedUserSilenceMiddleware())
    dp.include_router(common.router)
    dp.include_router(menus.router)
    dp.include_router(server.router)
    dp.include_router(vpn.router)
    dp.include_router(admin.router)


async def notify_admin_server_online():
    """Отправить уведомление о запуске бота."""
    from .config import get_admin_ids
    from .admin import is_admin_notification_enabled
    from .utils import get_external_ip
    
    bot = get_bot()
    admin_ids = get_admin_ids()
    server_ip = get_external_ip()
    
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
        
        if uptime_seconds < 120:
            event = "🔄 <b>Сервер был перезагружен!</b>"
        else:
            event = "⚡ <b>Бот был перезагружен!</b>"
    except Exception as e:
        print(f"Ошибка получения uptime: {e}")
        event = "📱 <b>Бот запущен</b>"
    
    text = f"""
{event}
<b>IP адрес сервера: </b> <code>{server_ip}</code>

Используйте /start для начала работы.
"""
    
    for admin in admin_ids:
        try:
            if not is_admin_notification_enabled(admin):
                continue
            await bot.send_message(admin, text, parse_mode="HTML")
        except Exception as e:
            print(f"Ошибка отправки уведомления: {e}")


async def update_bot_description():
    """Обновить описание бота."""
    from aiogram import Bot
    from .config import get_bot_token
    
    description = """

Привет! Я бот для управления OpenVPN и WireGuard. 
Вот что я могу сделать:
- Управлять пользователями (удаление/добавление).
- Генерировать и выдавать конфигурационные файлы.

Перейдите в главное меню (/start), чтобы начать.

"""
    
    token = get_bot_token()
    async with Bot(token=token) as bot:
        await bot.set_my_description(description, language_code="ru")


async def update_bot_about():
    """Обновить раздел «О боте»."""
    from aiogram import Bot
    from .config import get_bot_token
    
    about = "Бот для управления OpenVPN и WireGuard."
    
    token = get_bot_token()
    async with Bot(token=token) as bot:
        await bot.set_my_short_description(about, language_code="ru")


async def seed_bot_profile_if_needed():
    """Один раз задать описание и «о боте» """
    from .config import is_tg_bot_profile_seeded, mark_tg_bot_profile_seeded

    if is_tg_bot_profile_seeded():
        return
    await update_bot_description()
    await update_bot_about()
    mark_tg_bot_profile_seeded()


async def set_bot_commands():
    """Установить команды бота."""
    from aiogram import Bot
    from aiogram.types import BotCommand
    from .config import get_bot_token
    
    token = get_bot_token()
    async with Bot(token=token) as bot:
        commands = [
            BotCommand(command="start", description="Запустить бота"),
            BotCommand(command="id", description="Показать ваш Telegram ID"),
            BotCommand(command="request", description="Запросить доступ к боту"),
            BotCommand(command="client", description="Привязать клиента к ID"),
        ]
        await bot.set_my_commands(commands)


_last_load_alerts = {}

_vpn_service_last_state: dict[str, str] = {}
_vpn_pending_restart_tasks: dict[str, asyncio.Task] = {}
# unit -> {admin_chat_id: message_id} для редактирования после перезапуска
_vpn_inactive_alert_message_ids: dict[str, dict[int, int]] = {}

SYSTEM_STATS_DB_PATH = None


def cancel_pending_vpn_restart(service_unit: str) -> bool:
    """Отменить запланированный автоперезапуск unit (если таймер ещё не истёк)."""
    task = _vpn_pending_restart_tasks.get(service_unit)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def _notify_admins_vpn_service(bot, text: str, reply_markup=None):
    from .config import get_admin_ids
    from .admin import is_admin_notification_enabled, is_admin_vpn_service_notification_enabled
    
    for admin in get_admin_ids():
        if not is_admin_notification_enabled(admin):
            continue
        if not is_admin_vpn_service_notification_enabled(admin):
            continue
        try:
            await bot.send_message(admin, text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e:
            print(f"Ошибка уведомления о VPN-службе: {e}")


async def _send_vpn_inactive_alerts_and_store(
    service_unit: str, bot, text: str, reply_markup=None
) -> None:
    """Отправить предупреждение о неактивной службе и сохранить id сообщений для последующего edit."""
    from .config import get_admin_ids
    from .admin import is_admin_notification_enabled, is_admin_vpn_service_notification_enabled

    ids: dict[int, int] = {}
    for admin in get_admin_ids():
        if not is_admin_notification_enabled(admin):
            continue
        if not is_admin_vpn_service_notification_enabled(admin):
            continue
        try:
            msg = await bot.send_message(
                admin, text, parse_mode="HTML", reply_markup=reply_markup
            )
            ids[admin] = msg.message_id
        except Exception as e:
            print(f"Ошибка уведомления о VPN-службе: {e}")
    if ids:
        _vpn_inactive_alert_message_ids[service_unit] = ids


async def _edit_stored_vpn_inactive_alerts(
    service_unit: str,
    bot,
    text: str,
    reply_markup=None,
    *,
    fallback_send: bool = False,
) -> None:
    """Заменить текст ранее отправленных предупреждений; при отсутствии сохранённых id — опционально отправить новое."""
    from .admin import is_admin_notification_enabled, is_admin_vpn_service_notification_enabled

    stored = _vpn_inactive_alert_message_ids.pop(service_unit, None)
    if not stored:
        if fallback_send:
            await _notify_admins_vpn_service(bot, text, reply_markup=reply_markup)
        return

    for chat_id, message_id in stored.items():
        if not is_admin_notification_enabled(chat_id):
            continue
        if not is_admin_vpn_service_notification_enabled(chat_id):
            continue
        try:
            await bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=message_id,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        except Exception as e:
            print(f"Не удалось обновить уведомление о VPN-службе: {e}")
            try:
                await bot.send_message(
                    chat_id, text, parse_mode="HTML", reply_markup=reply_markup
                )
            except Exception as e2:
                print(f"Ошибка повторной отправки уведомления о VPN-службе: {e2}")


async def _vpn_notify_restart_outcome(service_unit: str, label: str, ok: bool, detail: str) -> None:
    bot = get_bot()
    if ok:
        _vpn_service_last_state[service_unit] = "active"
        text = (
            f"🔄 <b>Перезапуск выполнен</b>\n\n"
            f"Служба: <b>{label}</b>"
        )
    else:
        esc = str(detail).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = (
            f"❌ <b>Перезапуск не привёл к active</b>\n\n"
            f"<b>{label}</b>"
            f"Детали: <code>{esc}</code>"
        )
    await _edit_stored_vpn_inactive_alerts(
        service_unit, bot, text, reply_markup=None, fallback_send=True
    )


async def vpn_run_restart_now(service_unit: str, label: str) -> bool:
    """Отменить отложенный таймер и выполнить systemctl restart немедленно. Возвращает успех (после restart — active)."""
    cancel_pending_vpn_restart(service_unit)
    from .server import restart_systemd_service
    
    ok, detail = await restart_systemd_service(service_unit)
    await _vpn_notify_restart_outcome(service_unit, label, ok, detail)
    return ok


async def _vpn_autorestart_worker(service_unit: str, label: str):
    from .config import VPN_SERVICE_AUTORESTART_DELAY
    from .server import get_service_state, restart_systemd_service

    bot = get_bot()
    try:
        await asyncio.sleep(VPN_SERVICE_AUTORESTART_DELAY)
        if await get_service_state(service_unit) == "active":
            _vpn_service_last_state[service_unit] = "active"
            recovery_text = (
                f"✅ <b>Служба снова активна</b>\n\n"
                f"<b>{label}</b>"
            )
            await _edit_stored_vpn_inactive_alerts(
                service_unit, bot, recovery_text, reply_markup=None, fallback_send=False
            )
            return
        ok, detail = await restart_systemd_service(service_unit)
        await _vpn_notify_restart_outcome(service_unit, label, ok, detail)
    except asyncio.CancelledError:
        pass
    finally:
        _vpn_pending_restart_tasks.pop(service_unit, None)


async def monitor_vpn_services():
    """Проверка VPN unit systemd каждые VPN_SERVICE_CHECK_INTERVAL с."""
    from .config import (
        get_admin_ids,
        VPN_SERVICE_CHECK_INTERVAL,
        VPN_SERVICE_MONITOR_START_DELAY,
    )
    from .server import VPN_MONITORED_SERVICES, get_service_state
    from .keyboards import create_vpn_service_autorestart_cancel_keyboard
    
    bot = get_bot()
    await asyncio.sleep(VPN_SERVICE_MONITOR_START_DELAY)
    while not get_admin_ids():
        await asyncio.sleep(VPN_SERVICE_CHECK_INTERVAL)

    while True:
        if not get_admin_ids():
            await asyncio.sleep(VPN_SERVICE_CHECK_INTERVAL)
            continue
        for idx, (label, unit) in enumerate(VPN_MONITORED_SERVICES):
            state = await get_service_state(unit)
            prev = _vpn_service_last_state.get(unit)

            if state == "active":
                if prev is not None and prev != "active":
                    recovery_text = (
                        f"✅ <b>Служба снова активна</b>\n\n"
                        f"<b>{label}</b>"
                    )
                    await _edit_stored_vpn_inactive_alerts(
                        unit, bot, recovery_text, reply_markup=None, fallback_send=False
                    )
                pending = _vpn_pending_restart_tasks.get(unit)
                if pending and not pending.done():
                    pending.cancel()
                _vpn_service_last_state[unit] = state
                continue
            
            pending = _vpn_pending_restart_tasks.get(unit)
            if pending and not pending.done():
                _vpn_service_last_state[unit] = state
                continue

            kb = create_vpn_service_autorestart_cancel_keyboard(idx)
            text = (
                f"🔴 <b>Служба не активна</b>\n\n"
                f"Служба: <b>{label}</b>\n\n"
                f"Через <b>30 секунд</b> будет выполнен автоматический перезапуск\n\n"
                f"«Перезапустить сейчас» или «Отменить автоперезапуск» — кнопками ниже."
            )
            if unit not in _vpn_inactive_alert_message_ids:
                await _send_vpn_inactive_alerts_and_store(unit, bot, text, reply_markup=kb)
            task = asyncio.create_task(_vpn_autorestart_worker(unit, label))
            _vpn_pending_restart_tasks[unit] = task
            _vpn_service_last_state[unit] = state
        
        await asyncio.sleep(VPN_SERVICE_CHECK_INTERVAL)


def _get_system_stats_db_path():
    """Получить путь к system_stats.db (ленивая инициализация)."""
    global SYSTEM_STATS_DB_PATH
    if SYSTEM_STATS_DB_PATH is None:
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        SYSTEM_STATS_DB_PATH = os.path.join(base_dir, "databases", "system_stats.db")
    return SYSTEM_STATS_DB_PATH


def _check_sustained_high_load(cpu_threshold: int, memory_threshold: int) -> tuple:
    """
    Проверить, была ли нагрузка выше порога последние 5 минут (по данным БД).
    Возвращает (is_sustained, avg_cpu, avg_ram) или (False, None, None), если порог не превышен.
    """
    import sqlite3
    
    db_path = _get_system_stats_db_path()
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        now = datetime.datetime.now()
        five_minutes_ago = now - datetime.timedelta(minutes=5)
        
        cursor.execute(
            """
            SELECT cpu_percent, ram_percent, timestamp
            FROM system_stats
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
            """,
            (five_minutes_ago.strftime("%Y-%m-%d %H:%M:%S"),)
        )
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return False, None, None
        
        cpu_values = [row[0] for row in rows]
        ram_values = [row[1] for row in rows]
        
        cpu_above = sum(1 for cpu in cpu_values if cpu >= cpu_threshold)
        ram_above = sum(1 for ram in ram_values if ram >= memory_threshold)
        
        total_records = len(rows)
        
        cpu_sustained = cpu_above == total_records and total_records > 0
        ram_sustained = ram_above == total_records and total_records > 0
        
        if cpu_sustained or ram_sustained:
            avg_cpu = sum(cpu_values) / len(cpu_values)
            avg_ram = sum(ram_values) / len(ram_values)
            return True, avg_cpu, avg_ram
        
        return False, None, None
        
    except Exception as e:
        print(f"Ошибка чтения system_stats.db: {e}")
        return False, None, None


async def monitor_server_load():
    """Фоновая задача мониторинга нагрузки сервера по данным БД."""
    from .config import (
        get_admin_ids,
        get_load_thresholds,
        LOAD_CHECK_INTERVAL,
        LOAD_ALERT_COOLDOWN,
    )
    from .admin import is_admin_notification_enabled, is_admin_load_notification_enabled
    from .utils import get_color_by_percent
    
    while True:
        await asyncio.sleep(LOAD_CHECK_INTERVAL)
        admin_ids = get_admin_ids()
        
        if not admin_ids:
            continue
        
        cpu_threshold, memory_threshold = get_load_thresholds()
        
        is_sustained, avg_cpu, avg_ram = await asyncio.to_thread(
            _check_sustained_high_load, cpu_threshold, memory_threshold
        )
        
        if not is_sustained:
            continue
        
        now_ts = time.time()
        alert_text = (
            "<b>⚠️ Высокая нагрузка на сервер</b>\n"
            "<i>(держится более 5 минут)</i>\n\n"
            f"{get_color_by_percent(avg_cpu)} <b>ЦП:</b> {avg_cpu:>5.1f}%\n"
            f"{get_color_by_percent(avg_ram)} <b>ОЗУ:</b> {avg_ram:>5.1f}%"
        )
        
        bot = get_bot()
        for admin in admin_ids:
            if not is_admin_notification_enabled(admin):
                continue
            if not is_admin_load_notification_enabled(admin):
                continue
            last_sent = _last_load_alerts.get(admin, 0)
            if now_ts - last_sent < LOAD_ALERT_COOLDOWN:
                continue
            try:
                await bot.send_message(admin, alert_text, parse_mode="HTML")
                _last_load_alerts[admin] = now_ts
            except Exception as e:
                print(f"Ошибка отправки уведомления о нагрузке: {e}")
