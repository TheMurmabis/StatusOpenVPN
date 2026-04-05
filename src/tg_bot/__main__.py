"""Точка входа для запуска Telegram-бота"""

import asyncio

from .bot import (
    get_bot,
    get_dispatcher,
    notify_admin_server_online,
    seed_bot_profile_if_needed,
    set_bot_commands,
    monitor_server_load,
    monitor_vpn_services,
)


async def main():
    """Запустить бота в режиме long polling."""
    print("✅ Telegram bot starting...")
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
        print("\n🛑 Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
