"""Точка входа в Telegram bot для службы."""

import asyncio
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_script_dir)
if _root not in sys.path:
    sys.path.insert(0, _root)

from src.tg_bot.bot import (
    get_bot,
    get_dispatcher,
    notify_admin_server_online,
    seed_bot_profile_if_needed,
    set_bot_commands,
    monitor_server_load,
    monitor_vpn_services,
)


async def main():
    """Главная функция для запуска бота."""

    print("✅ Бот успешно запущен!")
    bot = get_bot()
    dp = get_dispatcher()
    try:
        await seed_bot_profile_if_needed()
        await notify_admin_server_online()
        await set_bot_commands()
        asyncio.create_task(monitor_server_load())
        asyncio.create_task(monitor_vpn_services())
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен!")


if __name__ == "__main__":
    asyncio.run(main())
