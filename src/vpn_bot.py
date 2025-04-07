import os
import re
import sys
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


# Проверяем, что переменные окружения корректны
if not BOT_TOKEN or BOT_TOKEN == "<Enter API Token>":
    print("Ошибка: BOT_TOKEN не задан или содержит значение по умолчанию.")
    sys.exit(1)

if not ADMIN_ID or ADMIN_ID == "<Enter your user ID>":
    print("Ошибка: ADMIN_ID не задан или содержит значение по умолчанию.")
    sys.exit(1)


class VPNSetup(StatesGroup):
    """Класс состояний для управления процессами настройки VPN через бота."""

    choosing_option = State()  # Состояние выбора опции (добавление/удаление клиента).
    entering_client_name = State()  # Состояние ввода имени клиента.
    entering_days = State()  # Состояние ввода количества дней для сертификата.
    deleting_client = State()  # Состояние подтверждения удаления клиента.
    list_for_delete = State()  # Состояние выбора клиента из списка для удаления.
    choosing_config_type = State()  # Состояние для выбора конфигурации
    choosing_protocol = State()  # Для выбора протокола OpenVPN
    choosing_wg_type = State()  # Для выбора типа WireGuard
    confirming_rename = State()  # Для подтверждения переименования файлов WireGuard


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
                InlineKeyboardButton(
                    text=f"🌐 Сервер: {SERVER_IP}", callback_data="no_action"
                ),
            ],
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
                InlineKeyboardButton(text="📝 Список клиентов", callback_data="3"),
                InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"),
            ],
        ]
    )


# Новые функции для создания меню выбора
def create_openvpn_config_menu(client_name: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="VPN", callback_data=f"openvpn_config_vpn_{client_name}"
                ),
                InlineKeyboardButton(
                    text="Antizapret",
                    callback_data=f"openvpn_config_antizapret_{client_name}",
                ),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_client_list")],
        ]
    )


def create_openvpn_protocol_menu(interface: str, client_name: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Стандартный (auto)",
                    callback_data=f"send_ovpn_{interface}_default_{client_name}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="TCP", callback_data=f"send_ovpn_{interface}_tcp_{client_name}"
                ),
                InlineKeyboardButton(
                    text="UDP", callback_data=f"send_ovpn_{interface}_udp_{client_name}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"back_to_interface_{interface}_{client_name}",
                )
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
                InlineKeyboardButton(text="📝 Список клиентов", callback_data="6"),
                InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"),
            ],
        ]
    )


def create_wireguard_config_menu(client_name: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="VPN", callback_data=f"wireguard_config_vpn_{client_name}"
                ),
                InlineKeyboardButton(
                    text="Antizapret",
                    callback_data=f"wireguard_config_antizapret_{client_name}",
                ),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_client_list")],
        ]
    )


def create_wireguard_type_menu(interface: str, client_name: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="WireGuard",
                    callback_data=f"send_wg_{interface}_wg_{client_name}",
                ),
                InlineKeyboardButton(
                    text="AmneziaWG",
                    callback_data=f"send_wg_{interface}_am_{client_name}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад", callback_data=f"back_to_interface_{client_name}"
                )
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


async def send_single_config(chat_id: int, path: str, caption: str):
    if os.path.exists(path):
        await bot.send_document(
            chat_id, document=FSInputFile(path), caption=f"🔐 {caption}"
        )
        return True
    return False


@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    """Обрабатывает команду /start и отображает главное меню."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("Доступ запрещен")
        return

    await message.answer("Главное меню:", reply_markup=create_main_menu())
    await state.set_state(VPNSetup.choosing_option)


@dp.callback_query(lambda c: c.data in ["main_menu", "openvpn_menu", "wireguard_menu"])
async def handle_main_menus(callback: types.CallbackQuery):
    if callback.data == "main_menu":
        await callback.message.edit_text(
            "Главное меню:", reply_markup=create_main_menu()
        )
    elif callback.data == "openvpn_menu":
        await callback.message.edit_text(
            "Меню OpenVPN:", reply_markup=create_openvpn_menu()
        )
    else:
        await callback.message.edit_text(
            "Меню WireGuard:", reply_markup=create_wireguard_menu()
        )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "no_action")
async def handle_no_action(callback: types.CallbackQuery):
    await callback.answer(
        "В разработке", show_alert=False
    )  # Просто закрываем всплывающее окно


@dp.callback_query(lambda c: c.data.startswith("client_"))
async def handle_client_selection(callback: types.CallbackQuery, state: FSMContext):
    _, vpn_type, client_name = callback.data.split("_", 2)
    await state.update_data(client_name=client_name, vpn_type=vpn_type)

    if vpn_type == "openvpn":
        await callback.message.edit_text(
            "Выберите тип конфигурации OpenVPN:",
            reply_markup=create_openvpn_config_menu(client_name),
        )
        await state.set_state(VPNSetup.choosing_config_type)
    else:
        await callback.message.edit_text(
            "Выберите тип конфигурации WireGuard:",
            reply_markup=create_wireguard_config_menu(client_name),
        )
        await state.set_state(VPNSetup.choosing_config_type)
    await callback.answer()


@dp.callback_query(VPNSetup.choosing_config_type)
async def handle_interface_selection(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    client_name = user_data["client_name"]
    vpn_type = user_data["vpn_type"]

    # Обработка кнопки "Назад"
    if callback.data == "back_to_client_list":
        clients = await get_clients(vpn_type)
        total_pages = (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

        await callback.message.edit_text(
            "Список клиентов:",
            reply_markup=create_client_list_keyboard(
                clients, 1, total_pages, vpn_type, "list"
            ),
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


@dp.callback_query(VPNSetup.choosing_protocol)
async def handle_protocol_selection(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    client_name = user_data["client_name"]

    if callback.data.startswith("send_ovpn_"):
        _, _, interface, proto, _ = callback.data.split("_", 4)
        file_name = (
            client_name.replace("antizapret-", "").replace("vpn-", "") + f"-{SERVER_IP}"
        )

        if proto == "default":
            path = f"/root/antizapret/client/openvpn/{interface}/{interface}-{file_name}.ovpn"
            caption = f"{interface}-{file_name}.ovpn"
        else:
            path = f"/root/antizapret/client/openvpn/{interface}-{proto}/{interface}-{file_name}-{proto}.ovpn"
            caption = f"{interface}-{file_name}-{proto}.ovpn"

        if await send_single_config(callback.from_user.id, path, caption):
            await callback.message.delete()
            await callback.message.answer(
                "Главное меню:", reply_markup=create_main_menu()
            )
            await state.clear()
        else:
            await callback.answer("❌ Файл не найден", show_alert=True)

    elif callback.data.startswith("back_to_interface_"):
        await handle_back_to_interface(callback, state)


@dp.callback_query(VPNSetup.choosing_wg_type)
async def handle_wg_type_selection(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    client_name = user_data["client_name"]

    # Обработка кнопки "Назад"
    if callback.data.startswith("back_to_interface_"):
        _, _, interface, client_name = callback.data.split("_", 3)
        await handle_back_to_interface(callback, state)  # Ваша функция для возврата
        await callback.answer()  # Важно: подтверждаем нажатие
        return

    if callback.data.startswith("send_wg_"):
        _, _, interface, wg_type, _ = callback.data.split("_", 4)

        full_ip = SERVER_IP  # Используем полный IP

        # Формируем имя файла без обрезки IP
        file_name = (
            f"{client_name.replace('antizapret-', '').replace('vpn-', '')}-{full_ip}"
        )

        # Формируем полный путь к файлу
        path = f"/root/antizapret/client/{'wireguard' if wg_type == 'wg' else 'amneziawg'}/{interface}/{interface}-{file_name}-{wg_type}.conf"

        # Проверяем существование файла сразу
        if not os.path.exists(path):
            # Попробуем найти файл без точного совпадения IP
            config_dir = f"/root/antizapret/client/{'wireguard' if wg_type == 'wg' else 'amneziawg'}/{interface}/"
            try:
                # Ищем файл по шаблону
                for f in os.listdir(config_dir):
                    if f.startswith(
                        f"{interface}-{client_name.replace('antizapret-', '').replace('vpn-', '')}"
                    ) and f.endswith(f"-{wg_type}.conf"):
                        path = os.path.join(config_dir, f)
                        break
            except Exception as e:
                print(f"Ошибка поиска файла: {e}")

        # Сохраняем данные для следующего шага
        await state.update_data(
            {
                "file_path": path,
                "original_name": os.path.basename(path),
                "short_name": f"{client_name.replace('antizapret-', '').replace('vpn-', '')}-{wg_type}.conf",
            }
        )

        # Проверяем существование файла еще раз
        if not os.path.exists(path):
            await callback.answer(
                f"❌ Файл конфигурации не найден: {os.path.basename(path)}",
                show_alert=True,
            )
            await state.clear()
            return

        await callback.message.edit_text(
            "Android может не принимать файлы с длинными именами.\nХотите переименовать файл при отправке?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Да", callback_data="confirm_rename"
                        ),
                        InlineKeyboardButton(text="❌ Нет", callback_data="no_rename"),
                    ]
                ]
            ),
        )
        await state.set_state(VPNSetup.confirming_rename)


@dp.callback_query(VPNSetup.confirming_rename)
async def handle_rename_confirmation(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    file_path = user_data["file_path"]

    # Проверяем, существует ли файл
    if not os.path.exists(file_path):
        print(f"Файл не найден: {file_path}")
        await callback.answer("❌ Файл не найден", show_alert=True)
        await state.clear()
        return

    # Проверяем размер файла (не пустой и не слишком большой)
    file_size = os.path.getsize(file_path)
    if file_size == 0:
        print(f"Файл пуст: {file_path}")
        await callback.answer("❌ Файл пуст", show_alert=True)
        await state.clear()
        return

    if file_size > 50 * 1024 * 1024:  # 50MB
        print(f"Файл слишком большой: {file_path} ({file_size} байт)")
        await callback.answer(
            "❌ Файл слишком большой для отправки в Telegram", show_alert=True
        )
        await state.clear()
        return

    try:
        if callback.data == "confirm_rename":
            file = FSInputFile(file_path, filename=user_data["short_name"])
            caption = f"🔐 {user_data['short_name']}"
        else:
            file = FSInputFile(file_path)
            caption = f"🔐 {user_data['original_name']}"

        await bot.send_document(
            chat_id=callback.from_user.id, document=file, caption=caption
        )

        await callback.message.delete()
        await callback.message.answer("Главное меню:", reply_markup=create_main_menu())

    except Exception as e:
        print(f"Ошибка при отправке файла: {e}")
        await callback.answer("❌ Ошибка при отправке файла", show_alert=True)

    await state.clear()


async def handle_back_to_interface(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    client_name = user_data["client_name"]
    vpn_type = user_data["vpn_type"]

    if vpn_type == "openvpn":
        await callback.message.edit_text(
            "Выберите тип конфигурации OpenVPN:",
            reply_markup=create_openvpn_config_menu(client_name),
        )
        await state.set_state(VPNSetup.choosing_config_type)
    else:
        await callback.message.edit_text(
            "Выберите тип конфигурации WireGuard:",
            reply_markup=create_wireguard_config_menu(client_name),
        )
        await state.set_state(VPNSetup.choosing_config_type)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("cancel_config_"))
async def handle_config_cancel(callback: types.CallbackQuery, state: FSMContext):
    client_name = callback.data.split("_")[-1]
    user_data = await state.get_data()
    vpn_type = user_data["vpn_type"]

    clients = await get_clients(vpn_type)
    total_pages = (len(clients) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    await callback.message.edit_text(
        "Список клиентов:",
        reply_markup=create_client_list_keyboard(
            clients, 1, total_pages, vpn_type, "list"
        ),
    )
    await state.clear()
    await callback.answer()


async def cleanup_openvpn_files(client_name: str):
    """Дополнительная очистка файлов OpenVPN после основного скрипта"""
    # Получаем имя файла без префиксов
    clean_name = client_name.replace("antizapret-", "").replace("vpn-", "")

    # Директории для проверки
    dirs_to_check = [
        "/root/antizapret/client/openvpn/antizapret/",
        "/root/antizapret/client/openvpn/antizapret-tcp/",
        "/root/antizapret/client/openvpn/antizapret-udp/",
        "/root/antizapret/client/openvpn/vpn/",
        "/root/antizapret/client/openvpn/vpn-tcp/",
        "/root/antizapret/client/openvpn/vpn-udp/",
    ]

    deleted_files = []

    for dir_path in dirs_to_check:
        if not os.path.exists(dir_path):
            continue

        for filename in os.listdir(dir_path):
            # Удаляем все файлы, содержащие имя клиента
            if clean_name in filename:
                try:
                    file_path = os.path.join(dir_path, filename)
                    os.remove(file_path)
                    deleted_files.append(file_path)
                except Exception as e:
                    print(f"Ошибка удаления {file_path}: {e}")

    return deleted_files


@dp.callback_query()
async def handle_callback_query(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает нажатия на кнопки в Telegram боте и выполняет соответствующие действия."""
    data = callback.data
    user_id = callback.from_user.id

    try:
        if user_id != ADMIN_ID:
            await callback.answer("Доступ запрещен!")
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

            try:
                result = await execute_script(option, client_name)

                # Для OpenVPN делаем дополнительную очистку
                if vpn_type == "openvpn" and result["returncode"] == 0:
                    deleted_files = await cleanup_openvpn_files(client_name)
                    if deleted_files:
                        result["additional_deleted"] = deleted_files

                # Формируем сообщение о результате
                if result["returncode"] == 0:
                    msg = f"✅ Клиент {client_name} удален!"
                    if vpn_type == "openvpn" and result.get("additional_deleted"):
                        msg += f"\nДополнительно удалено файлов: {len(result['additional_deleted'])}"

                    await callback.message.edit_text(msg)
                    await callback.message.answer(
                        "Главное меню:", reply_markup=create_main_menu()
                    )
                else:
                    await callback.message.edit_text(f"❌ Ошибка: {result['stderr']}")

            except Exception as e:
                print(f"Ошибка при удалении клиента: {e}")

            finally:
                await callback.answer()
                await state.clear()

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
            # file_name = file_name[:18]
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
async def send_backup(chat_id: int) -> bool:
    """Функция отправки резервной копии"""

    paths_to_check = [
        f"/root/antizapret/backup-{SERVER_IP}.tar.gz",
        "/root/antizapret/backup.tar.gz"
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

    return False  # Если ни один файл не найден


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
