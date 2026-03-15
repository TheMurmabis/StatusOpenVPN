"""Точка входа для запуска Telegram-бота"""

import asyncio

from .bot import (
    get_bot,
    get_dispatcher,
    notify_admin_server_online,
    update_bot_description,
    update_bot_about,
    set_bot_commands,
    monitor_server_load,
)


async def main():
    """Запустить бота в режиме long polling."""
    print("✅ Telegram bot starting...")
    bot = get_bot()
    dp = get_dispatcher()
    try:
        await update_bot_description()
        await notify_admin_server_online()
        await update_bot_about()
        await set_bot_commands()
        asyncio.create_task(monitor_server_load())
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
