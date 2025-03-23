import os
import re
import requests
import asyncio

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    FSInputFile,
    BotCommand,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties

load_dotenv()

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
ITEMS_PER_PAGE = 5

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


class VPNSetup(StatesGroup):
    """Класс состояний для управления процессами настройки VPN через бота."""

    choosing_option = State()  # Состояние выбора опции (добавление/удаление клиента).
    entering_client_name = State()  # Состояние ввода имени клиента.
    entering_days = State()  # Состояние ввода количества дней для сертификата.
    deleting_client = State()  # Состояние подтверждения удаления клиента.
    list_for_delete = State()  # Состояние выбора клиента из списка для удаления.


# Описание для вашего бота
BOT_DESCRIPTION = """

Привет! Я бот для управления OpenVPN и WireGuard. 
Вот что я могу сделать:
- Управлять пользователями (удаление/добавление).
- Генерировать и выдавать конфигурационные файлы.

Перейдите в главное меню (/start), чтобы начать.

"""


async def update_bot_description():
    """
    Асинхронная функция для обновления описания бота.

    Описание устанавливается для русского языка ("ru").
    """
    async with Bot(token=BOT_TOKEN) as bot:
        await bot.set_my_description(BOT_DESCRIPTION, language_code="ru")


BOT_ABOUT = "Бот для управления OpenVPN и WireGuard."


async def update_bot_about():
    """Асинхронная функция для обновления раздела «О боте»."""
    async with Bot(token=BOT_TOKEN) as bot:
        await bot.set_my_short_description(BOT_ABOUT, language_code="ru")


async def set_bot_commands():
    """
    Асинхронная функция для установки списка команд бота.
    """
    async with Bot(token=BOT_TOKEN) as bot:
        commands = [
            BotCommand(command="start", description="Запустить бота"),
        ]

        await bot.set_my_commands(commands)


def get_external_ip():
    try:
        response = requests.get("https://api.ipify.org", timeout=10)
        if response.status_code == 200:
            return response.text
        return "IP не найден"
    except requests.Timeout:
        return "Ошибка: запрос превысил время ожидания."
    except requests.ConnectionError:
        return "Ошибка: нет подключения к интернету."
    except requests.RequestException as e:
        return f"Ошибка при запросе: {e}"


SERVER_IP = get_external_ip()


def create_main_menu():
    """Создает главное меню в виде InlineKeyboardMarkup."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="OpenVPN", callback_data="openvpn_menu"),
                InlineKeyboardButton(text="WireGuard", callback_data="wireguard_menu"),
            ],
            [
                InlineKeyboardButton(text="🔄 Пересоздать файлы", callback_data="7"),
                InlineKeyboardButton(text="📦 Создать бэкап", callback_data="8"),
            ],
        ]
    )


def create_openvpn_menu():
    """Создает меню OpenVPN в виде InlineKeyboardMarkup."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🆕 Создать клиента", callback_data="1"),
                InlineKeyboardButton(text="❌ Удалить клиента", callback_data="2"),
            ],
            [
                InlineKeyboardButton(text="Список клиентов", callback_data="3"),
                InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"),
            ],
        ]
    )


def create_wireguard_menu():
    """Создает меню WireGuard в виде InlineKeyboardMarkup."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🆕 Создать клиента", callback_data="4"),
                InlineKeyboardButton(text="❌ Удалить клиента", callback_data="5"),
            ],
            [
                InlineKeyboardButton(text="Список клиентов", callback_data="6"),
                InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"),
            ],
        ]
    )


def create_client_list_keyboard(clients, page, total_pages, vpn_type, action):
    """Создает клавиатуру с клиентами VPN."""
    buttons = []
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE

    for client in clients[start_idx:end_idx]:
        prefix = "delete" if action == "delete" else "client"
        callback_data = f"{action}_{vpn_type}_{client}"

        if action == "delete":
            callback_data = f"delete_{vpn_type}_{client}"
        else:  # действие "client" (выдача конфигурационного файла)
            callback_data = f"client_{vpn_type}_{client}"

        buttons.append([InlineKeyboardButton(text=client, callback_data=callback_data)])

    pagination = []
    if page > 1:
        pagination.append(
            InlineKeyboardButton(
                text="⬅️ Предыдущая", callback_data=f"page_{action}_{vpn_type}_{page-1}"
            )
        )
    if page < total_pages:
        pagination.append(
            InlineKeyboardButton(
                text="Следующая ➡️", callback_data=f"page_{action}_{vpn_type}_{page+1}"
            )
        )

    if pagination:
        buttons.append(pagination)

    buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{vpn_type}_menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_confirmation_keyboard(client_name, vpn_type):
    """Создает клавиатуру подтверждения удаления клиента."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"confirm_{vpn_type}_{client_name}",
                ),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete"),
            ]
        ]
    )


async def execute_script(option: str, client_name: str = None, days: str = None):
    """Выполняет shell-скрипт для управления VPN-клиентами."""
    # Путь к скрипту
    script_path = "/root/antizapret/client.sh"
    
    # Проверяем, существует ли файл
    if not os.path.exists(script_path):
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": f"❌ Файл {script_path} не найден! Убедитесь, что скрипт client.sh существует.",
        }

    # Формируем команду
    command = f"{script_path} {option}"
    if option not in ["8", "7"] and client_name:
        clean_name = client_name.replace("antizapret-", "").replace("vpn-", "")
        command += f" {client_name}"
        if days and option == "1":
            command += f" {days}"

    try:
        # Указываем окружение, включая правильный $PATH
        env = os.environ.copy()
        env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

        # Выполняем команду с указанным окружением
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,  # Передаем окружение
        )

        stdout, stderr = await process.communicate()
        return {
            "returncode": process.returncode,
            "stdout": stdout.decode().strip(),
            "stderr": stderr.decode().strip(),
        }
    except Exception as e:
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": f"❌ Ошибка при выполнении скрипта: {str(e)}",
        }


@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    """Обрабатывает команду /start и отображает главное меню."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("Доступ запрещен")
        return

    await message.answer("Главное меню:", reply_markup=create_main_menu())
    await state.set_state(VPNSetup.choosing_option)


@dp.callback_query()
async def handle_callback_query(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает нажатия на кнопки в Telegram боте и выполняет соответствующие действия."""
    data = callback.data
    user_id = callback.from_user.id

    try:
        if user_id != ADMIN_ID:
            await callback.answer("Доступ запрещен")
            return

        # Навигация по меню
        if data == "main_menu":
            await callback.message.edit_text(
                "Главное меню:", reply_markup=create_main_menu()
            )
            await callback.answer()
            return

        if data == "openvpn_menu":
            await callback.message.edit_text(
                "Меню OpenVPN:", reply_markup=create_openvpn_menu()
            )
            await callback.answer()
            return

        if data == "wireguard_menu":
            await callback.message.edit_text(
                "Меню WireGuard:", reply_markup=create_wireguard_menu()
            )
            await callback.answer()
            return

        # Обработка выбора клиента из списка
        if data.startswith("client_"):
            _, vpn_type, client_name = data.split("_", 2)

            # Определяем тип конфига для отправки
            option = "1" if vpn_type == "openvpn" else "4"

            # Отправляем файл конфигурации
            await send_config(callback.from_user.id, client_name, option)
            await callback.answer()

            # Возвращаемся в предыдущее меню
            await callback.message.edit_text(
                "Главное меню:", reply_markup=create_main_menu()
            )
            return

        # Пагинация
        if data.startswith("page_"):
            # Разбираем callback_data с учетом action
            _, action, vpn_type, page = data.split("_", 3)
            page = int(page)
            clients = await get_clients(vpn_type)
            total_pages = (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
            await callback.message.edit_text(
                "Список клиентов:",
                reply_markup=create_client_list_keyboard(
                    clients, page, total_pages, vpn_type, action  # Добавляем action
                ),
            )
            await callback.answer()
            return

        # Обработка удаления
        if data.startswith("delete_"):
            _, vpn_type, client_name = data.split("_", 2)
            await callback.message.edit_text(
                f"❓ Удалить клиента {client_name} ({vpn_type})?",
                reply_markup=create_confirmation_keyboard(client_name, vpn_type),
            )
            await callback.answer()
            return

        # Обработка пагинации для удаления
        if data.startswith("page_delete_"):
            _, _, vpn_type, page = data.split("_")
            page = int(page)
            clients = await get_clients(vpn_type)
            total_pages = (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

            await callback.message.edit_text(
                "Выберите клиента для удаления:",
                reply_markup=create_client_list_keyboard(
                    clients, page, total_pages, vpn_type, "delete"
                ),
            )
            await callback.answer()
            return

        # Инициализация удаления
        if data in ["2", "5"]:
            vpn_type = "openvpn" if data == "2" else "wireguard"
            clients = await get_clients(vpn_type)

            if not clients:
                await callback.message.edit_text("❌ Нет клиентов для удаления")
                return

            total_pages = (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
            await callback.message.edit_text(
                "Выберите клиента для удаления:",
                reply_markup=create_client_list_keyboard(
                    clients, 1, total_pages, vpn_type, "delete"
                ),
            )
            await state.set_state(VPNSetup.list_for_delete)
            await callback.answer()
            return

        # Подтверждение удаления
        if data.startswith("confirm_"):
            _, vpn_type, client_name = data.split("_", 2)
            option = "2" if vpn_type == "openvpn" else "5"
            result = await execute_script(option, client_name)

            if result["returncode"] == 0:
                await callback.message.edit_text(f"✅ Клиент {client_name} удален!")
                await callback.message.answer(
                    "Главное меню:", reply_markup=create_main_menu()
                )

            else:
                await callback.message.edit_text(f"❌ Ошибка: {result['stderr']}")
            await callback.answer()
            return

        if data == "cancel_delete":
            await callback.message.edit_text(
                "❌ Удаление отменено", reply_markup=create_main_menu()
            )
            await callback.answer()
            return

        # Список клиентов
        if data in ["3", "6"]:
            vpn_type = "openvpn" if data == "3" else "wireguard"
            clients = await get_clients(vpn_type)
            total_pages = (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
            await callback.message.edit_text(
                "Список клиентов:",
                reply_markup=create_client_list_keyboard(
                    clients, 1, total_pages, vpn_type, "list"  # Добавляем action="list"
                ),
            )
            await callback.answer()
            return

        # Удаление клиента
        if data in ["2", "5"]:
            await state.update_data(action=data)
            await callback.message.edit_text("Введите имя клиента для удаления:")
            await state.set_state(VPNSetup.deleting_client)
            await callback.answer()
            return

        # Создание клиента
        if data in ["1", "4"]:
            await state.update_data(action=data)
            await callback.message.edit_text("Введите имя нового клиента:")
            await state.set_state(VPNSetup.entering_client_name)
            await callback.answer()
            return

        # Пересоздание файлов
        if data == "7":
            await callback.message.edit_text("⏳ Идет пересоздание файлов...")
            result = await execute_script("7")
            if result["returncode"] == 0:
                await callback.message.edit_text("✅ Файлы успешно пересозданы!")
                await callback.message.answer(
                    "Главное меню:", reply_markup=create_main_menu()
                )
            else:
                await callback.message.edit_text(f"❌ Ошибка: {result['stderr']}")
            await callback.answer()
            return

        # Создание бэкапа
        if data == "8":
            await callback.message.edit_text("⏳ Создаю бэкап...")
            result = await execute_script("8")

            if result["returncode"] == 0:
                # Пытаемся отправить бэкап
                if await send_backup(callback.from_user.id):
                    await callback.message.delete()  # Удаляем сообщение "Создаю бэкап"
                    await callback.message.answer(
                        "Главное меню:", reply_markup=create_main_menu()
                    )
                else:
                    await callback.message.edit_text("❌ Не удалось отправить бэкап")
            else:
                await callback.message.edit_text(
                    f"❌ Ошибка при создании бэкапа: {result['stderr']}"
                )

            await callback.answer()
            return

    except Exception as e:
        print(f"Error: {e}")
        await callback.answer("⚠️ Произошла ошибка!")


@dp.message(VPNSetup.entering_client_name)
async def handle_client_name(message: types.Message, state: FSMContext):
    """Обрабатывает ввод имени клиента в боте."""
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
            await send_config(message.chat.id, client_name, option)
            await message.answer("✅ Клиент создан!")
            await message.answer("Главное меню:", reply_markup=create_main_menu())
        else:
            await message.answer(f"❌ Ошибка: {result['stderr']}")
        await state.clear()


@dp.message(VPNSetup.entering_days)
async def handle_days(message: types.Message, state: FSMContext):
    """Обрабатывает ввод количества дней для создания клиента в боте."""
    days = message.text.strip()
    if not days.isdigit() or not (1 <= int(days) <= 3650):
        await message.answer("❌ Введите число от 1 до 3650")
        return

    data = await state.get_data()
    client_name = data["client_name"]
    result = await execute_script("1", client_name, days)

    if result["returncode"] == 0:
        await send_config(message.chat.id, client_name, "1")
        await message.answer("✅ Клиент создан!", reply_markup=create_main_menu())
    else:
        await message.answer(f"❌ Ошибка: {result['stderr']}")
    await state.clear()


@dp.message(VPNSetup.deleting_client)
async def handle_delete_client(message: types.Message, state: FSMContext):
    """Обрабатывает запрос на удаление клиента в боте."""
    client_name = message.text.strip()
    data = await state.get_data()
    vpn_type = "openvpn" if data["action"] == "2" else "wireguard"

    await message.answer(
        f"Вы уверены, что хотите удалить клиента {client_name}?",
        reply_markup=create_confirmation_keyboard(client_name, vpn_type),
    )
    await state.clear()


async def get_clients(vpn_type: str):
    option = "3" if vpn_type == "openvpn" else "6"
    result = await execute_script(option)

    if result["returncode"] == 0:
        # Фильтруем строки, убирая заголовки и пустые строки
        clients = [
            c.strip()
            for c in result["stdout"].split("\n")
            if c.strip()  # Убираем пустые строки
            and not c.startswith(
                "OpenVPN existing client names:"
            )  # Убираем заголовок OpenVPN
            and not c.startswith(
                "WireGuard/AmneziaWG existing client names:"
            )  # Убираем заголовок WireGuard
            and not c.startswith(
                "OpenVPN - List clients"
            )  # Убираем строку "OpenVPN - List clients"
            and not c.startswith(
                "WireGuard/AmneziaWG - List clients"
            )  # Убираем строку "WireGuard/AmneziaWG - List clients"
        ]
        return clients
    return []


async def send_config(chat_id: int, client_name: str, option: str):
    """Функция отправки конфига"""
    try:
        # Формируем имя файла согласно логике client.sh
        file_name = client_name.replace("antizapret-", "").replace("vpn-", "")
        file_name = f"{file_name}-{SERVER_IP}"

        # Применяем обрезку как в оригинальном скрипте
        if option == "4":  # WireGuard
            file_name = file_name[:18]
            path = f"/root/antizapret/client/amneziawg/antizapret/antizapret-{file_name}-am.conf"
        else:  # OpenVPN
            path = f"/root/antizapret/client/openvpn/antizapret/antizapret-{file_name}.ovpn"

        # Ожидание файла
        timeout = 25
        interval = 0.5
        elapsed = 0

        while not os.path.exists(path) and elapsed < timeout:
            await asyncio.sleep(interval)
            elapsed += interval

        if os.path.exists(path):
            await bot.send_document(
                chat_id,
                document=FSInputFile(path),
                caption=f"🔐 Конфигурация {client_name}",
            )
        else:
            await bot.send_message(chat_id, "❌ Файл конфигурации не найден")

    except Exception as e:
        print(f"Ошибка: {e}")
        await bot.send_message(chat_id, "⚠️ Ошибка при отправке конфигурации")


# Добавляем функцию send_backup здесь
async def send_backup(chat_id: int):
    """Функция отправки резервной копии"""

    backup_path = "/root/antizapret/backup.tar.gz"
    try:
        if os.path.exists(backup_path):
            await bot.send_document(
                chat_id=chat_id,
                document=FSInputFile(backup_path),
                caption="📦 Бэкап клиентов",
            )
            return True
        return False
    except Exception as e:
        print(f"Ошибка отправки бэкапа: {e}")
        return False


async def main():
    """Главная функция для запуска бота."""
    print("✅ Бот успешно запущен!")
    try:
        await update_bot_description()
        await update_bot_about()
        await set_bot_commands()
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
