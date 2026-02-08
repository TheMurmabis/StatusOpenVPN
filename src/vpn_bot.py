import datetime
import json
import os
import re
import sys
import psutil
import requests
import asyncio
import time

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

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from main import (
    get_uptime,
    format_uptime,
    count_online_clients,
    parse_relative_time,
    is_peer_online,
    read_wg_config,
)

load_dotenv()

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = [int(x) for x in os.getenv("ADMIN_ID", "").split(",") if x.strip().isdigit()]
ITEMS_PER_PAGE = 5
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
CLIENT_MAPPING_KEY = "CLIENT_MAPPING"
DEFAULT_CPU_ALERT_THRESHOLD = 90
DEFAULT_MEMORY_ALERT_THRESHOLD = 60
LOAD_CHECK_INTERVAL = 60
LOAD_ALERT_COOLDOWN = 30 * 60

last_load_alerts = {}

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


def load_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as settings_file:
            data = json.load(settings_file)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("telegram_admins", {})
    data.setdefault("telegram_clients", {})
    if not isinstance(data.get("telegram_admins"), dict):
        data["telegram_admins"] = {}
    if not isinstance(data.get("telegram_clients"), dict):
        data["telegram_clients"] = {}
    return data


def save_settings(data):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as settings_file:
        json.dump(data, settings_file, ensure_ascii=False, indent=4)
        settings_file.write("\n")


def read_env_values():
    values = {}
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except FileNotFoundError:
        return values
    return values


def update_env_values(updates):
    updates = {key: value for key, value in updates.items() if key}
    if not updates:
        return

    updated_keys = set()
    lines = []
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as env_file:
            lines = env_file.readlines()
    except FileNotFoundError:
        lines = []

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        key, _ = line.split("=", 1)
        key = key.strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}\n")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as env_file:
        env_file.writelines(new_lines)


def update_admin_info(user: types.User):
    if not user:
        return

    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        admin_map = {}
    user_id = str(user.id)
    display_name = " ".join(
        [part for part in [user.first_name, user.last_name] if part]
    ).strip()
    username = (user.username or "").strip()

    existing = admin_map.get(user_id, {})
    if not display_name:
        display_name = existing.get("display_name", "")
    if not username:
        username = existing.get("username", "")
    notify_enabled = existing.get("notify_enabled", True)
    notify_load_enabled = existing.get("notify_load_enabled", True)

    admin_map[user_id] = {
        "display_name": display_name,
        "username": username,
        "notify_enabled": notify_enabled,
        "notify_load_enabled": notify_load_enabled,
    }
    data["telegram_admins"] = admin_map
    save_settings(data)


def get_client_mapping():
    env_values = read_env_values()
    raw_value = env_values.get(CLIENT_MAPPING_KEY, "")
    mapping = {}
    if not raw_value:
        return mapping
    for item in raw_value.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        telegram_id, client_name = item.split(":", 1)
        telegram_id = telegram_id.strip()
        client_name = client_name.strip()
        if not telegram_id or not client_name:
            continue
        mapping[telegram_id] = client_name
    return mapping


def get_client_name_for_user(user_id: int):
    return get_client_mapping().get(str(user_id))


def set_client_mapping(telegram_id: str, client_name: str):
    client_map = get_client_mapping()
    client_map[str(telegram_id)] = client_name
    serialized = ",".join([f"{key}:{value}" for key, value in client_map.items()])
    update_env_values({CLIENT_MAPPING_KEY: serialized})


def remove_client_mapping(telegram_id: str):
    client_map = get_client_mapping()
    if str(telegram_id) in client_map:
        client_map.pop(str(telegram_id), None)
    serialized = ",".join([f"{key}:{value}" for key, value in client_map.items()])
    update_env_values({CLIENT_MAPPING_KEY: serialized})


def is_admin_notification_enabled(user_id: int) -> bool:
    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        return True
    admin_entry = admin_map.get(str(user_id), {})
    if not isinstance(admin_entry, dict):
        return True
    return bool(admin_entry.get("notify_enabled", True))


def set_admin_notification(user_id: int, enabled: bool):
    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        admin_map = {}
    admin_entry = admin_map.get(str(user_id), {})
    if not isinstance(admin_entry, dict):
        admin_entry = {}
    admin_entry["notify_enabled"] = bool(enabled)
    admin_map[str(user_id)] = admin_entry
    data["telegram_admins"] = admin_map
    save_settings(data)


def is_admin_load_notification_enabled(user_id: int) -> bool:
    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        return True
    admin_entry = admin_map.get(str(user_id), {})
    if not isinstance(admin_entry, dict):
        return True
    return bool(admin_entry.get("notify_load_enabled", True))


def set_admin_load_notification(user_id: int, enabled: bool):
    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        admin_map = {}
    admin_entry = admin_map.get(str(user_id), {})
    if not isinstance(admin_entry, dict):
        admin_entry = {}
    admin_entry["notify_load_enabled"] = bool(enabled)
    admin_map[str(user_id)] = admin_entry
    data["telegram_admins"] = admin_map
    save_settings(data)


def get_load_thresholds():
    data = load_settings()
    thresholds = data.get("load_thresholds") or {}
    if not isinstance(thresholds, dict):
        thresholds = {}
    cpu_threshold = thresholds.get("cpu", DEFAULT_CPU_ALERT_THRESHOLD)
    memory_threshold = thresholds.get("memory", DEFAULT_MEMORY_ALERT_THRESHOLD)
    return cpu_threshold, memory_threshold


def set_load_thresholds(cpu_threshold: int = None, memory_threshold: int = None):
    data = load_settings()
    thresholds = data.get("load_thresholds") or {}
    if not isinstance(thresholds, dict):
        thresholds = {}
    if cpu_threshold is not None:
        thresholds["cpu"] = int(cpu_threshold)
    if memory_threshold is not None:
        thresholds["memory"] = int(memory_threshold)
    data["load_thresholds"] = thresholds
    save_settings(data)


# Проверяем, что переменные окружения корректны
if not BOT_TOKEN or BOT_TOKEN == "<Enter API Token>":
    print("Ошибка: BOT_TOKEN не задан или содержит значение по умолчанию.")
    sys.exit(1)

if not ADMIN_ID or ADMIN_ID == "<Enter your user ID>":
    print(
        "Предупреждение: ADMIN_ID не задан. Бот запущен в режиме первичной настройки."
    )


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
    entering_client_mapping = State()  # Состояние для привязки клиента к Telegram ID
    entering_cpu_threshold = State()  # Ввод порога CPU
    entering_memory_threshold = State()  # Ввод порога RAM


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
            BotCommand(command="id", description="Показать ваш Telegram ID"),
            BotCommand(command="client", description="Привязать клиента к ID"),
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
                    text=f"ℹ️ Меню сервера: {SERVER_IP}", callback_data="server_menu"
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
            [
                InlineKeyboardButton(text="👥 Клиенты бота", callback_data="clients_menu"),
                InlineKeyboardButton(
                    text="👤 Администраторы", callback_data="admins_menu"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔔 Уведомления", callback_data="notifications_menu"
                ),
            ],
        ]
    )


def create_server_menu():
    """Создает меню управления сервером."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Статистика", callback_data="server_stats"
                ),
                InlineKeyboardButton(
                    text="🔄 Перезагрузка", callback_data="server_reboot"
                ),
            ],
            [
                InlineKeyboardButton(text="⚙️ Службы", callback_data="server_services"),
                InlineKeyboardButton(
                    text="👥 Кто онлайн", callback_data="server_online"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚠️ Пороги нагрузки", callback_data="server_thresholds"
                ),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"),
            ],
        ]
    )


def create_thresholds_menu():
    cpu_threshold, memory_threshold = get_load_thresholds()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"CPU: {cpu_threshold}%",
                    callback_data="server_thresholds",
                ),
                InlineKeyboardButton(
                    text="Изменить CPU", callback_data="set_cpu_threshold"
                ),

            ],
            [
                InlineKeyboardButton(
                    text=f"RAM: {memory_threshold}%",
                    callback_data="server_thresholds",
                ),
                InlineKeyboardButton(
                    text="Изменить RAM", callback_data="set_memory_threshold"
                ),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="server_menu"),
            ],
        ]
    )


def create_reboot_confirm_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить перезагрузку",
                    callback_data="server_reboot_confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена", callback_data="server_menu"
                )
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
def create_openvpn_config_menu(client_name: str, back_callback: str = "back_to_client_list"):
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
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
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


def create_wireguard_config_menu(client_name: str, back_callback: str = "back_to_client_list"):
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
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
        ]
    )


def create_client_menu(client_name: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="OpenVPN", callback_data=f"client_openvpn_{client_name}"
                ),
                InlineKeyboardButton(
                    text="WireGuard", callback_data=f"client_wireguard_{client_name}"
                ),
            ],
        ]
    )


def create_notifications_menu(user_id: int):
    enabled = is_admin_notification_enabled(user_id)
    load_enabled = is_admin_load_notification_enabled(user_id)
    status_text = "вкл ✅" if enabled else "выкл ❌"
    toggle_text = "Выкл" if enabled else "Вкл"
    load_status = "вкл ✅" if load_enabled else "выкл ❌"
    load_toggle_text = "Выкл" if load_enabled else "Вкл"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🔔 Уведомления: {status_text}",
                    callback_data="toggle_notifications",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"⚠️ Нагрузка: {load_status}",
                    callback_data="toggle_load_notifications",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")],
        ]
    )


async def show_client_menu(message: types.Message, user_id: int):
    client_name = get_client_name_for_user(user_id)
    if not client_name:
        await message.answer(
            "Доступ запрещен. Передайте администратору ваш ID: "
            f"<code>{user_id}</code>"
        )
        return
    await message.answer(
        f'Ваш клиент: "{client_name}". Выберите протокол:',
        reply_markup=create_client_menu(client_name),
    )


def get_user_label(telegram_id: str) -> str:
    data = load_settings()
    admin_map = data.get("telegram_admins") or {}
    if not isinstance(admin_map, dict):
        admin_map = {}
    entry = admin_map.get(str(telegram_id), {})
    if isinstance(entry, dict):
        username = (entry.get("username") or "").strip()
        if username:
            return f"@{username}"
    return str(telegram_id)


def create_clients_menu():
    client_map = get_client_mapping()
    buttons = []
    if client_map:
        for telegram_id, client_name in client_map.items():
            label = f"{get_user_label(telegram_id)}:{client_name}"
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=f"clientmap_{telegram_id}",
                    )
                ]
            )
    else:
        buttons.append(
            [InlineKeyboardButton(text="Привязок нет", callback_data="no_action")]
        )

    buttons.append(
        [InlineKeyboardButton(text="➕ Добавить", callback_data="clientmap_add")]
    )
    buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_admins_menu():
    buttons = []
    if ADMIN_ID:
        for admin_id in ADMIN_ID:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=get_user_label(str(admin_id)),
                        callback_data="no_action",
                    )
                ]
            )
    else:
        buttons.append(
            [InlineKeyboardButton(text="Администраторы не настроены", callback_data="no_action")]
        )

    buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_clientmap_delete_menu(telegram_id: str, client_name: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Удалить",
                    callback_data=f"clientmap_delete_confirm_{telegram_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="clients_menu",
                ),
            ]
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
    update_admin_info(message.from_user)
    if not ADMIN_ID:
        await message.answer(
            "Администраторы еще не настроены.\n"
            "Ваш ID для настройки: "
            f"<code>{message.from_user.id}</code>\n"
            "Добавьте его в переменную <b>ADMIN_ID</b> в .env."
        )
        await state.clear()
        return

    if message.from_user.id in ADMIN_ID:
        await message.answer("Главное меню:", reply_markup=create_main_menu())
        await state.set_state(VPNSetup.choosing_option)
        return

    client_name = get_client_name_for_user(message.from_user.id)
    if not client_name:
        await message.answer(
            "Доступ запрещен. Передайте администратору ваш ID: "
            f"<code>{message.from_user.id}</code>"
        )
        return

    await show_client_menu(message, message.from_user.id)
    await state.clear()


@dp.message(Command("id"))
async def show_user_id(message: types.Message):
    update_admin_info(message.from_user)
    await message.answer(f"Ваш ID: <code>{message.from_user.id}</code>")


@dp.message(Command("client"))
async def handle_client_mapping_command(message: types.Message, state: FSMContext):
    update_admin_info(message.from_user)
    if message.from_user.id not in ADMIN_ID:
        await message.answer("Доступ запрещен")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Отправьте привязку в формате:\n"
            "<code>client_id:имя_клиента</code>\n"
            "Например: <code>123456789:vpn-user</code>"
        )
        await state.set_state(VPNSetup.entering_client_mapping)
        return

    await process_client_mapping(message, parts[1], state)


@dp.message(VPNSetup.entering_client_mapping)
async def handle_client_mapping_state(message: types.Message, state: FSMContext):
    update_admin_info(message.from_user)
    if message.from_user.id not in ADMIN_ID:
        await message.answer("Доступ запрещен")
        await state.clear()
        return

    success = await process_client_mapping(message, message.text, state)
    if success:
        await message.answer("Привязки клиентов:", reply_markup=create_clients_menu())


async def process_client_mapping(message: types.Message, raw_text: str, state: FSMContext):
    payload = raw_text.strip()
    match = re.match(r"^(\d+)\s*:\s*([a-zA-Z0-9_-]{1,32})$", payload)
    if not match:
        await message.answer(
            "❌ Некорректный формат. Используйте:\n"
            "<code>client_id:имя_клиента</code>"
        )
        return False

    telegram_id, client_name = match.groups()
    set_client_mapping(telegram_id, client_name)
    await message.answer(
        f"✅ Привязка сохранена: <code>{telegram_id}</code> → <b>{client_name}</b>"
    )
    await state.clear()
    return True

async def notify_admin_server_online():
    """Отправляем уведомление о запуске/перезапуске бота."""
    
    now = datetime.datetime.now()
    
    # Получаем uptime системы
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
<b>IP адрес сервера: </b> <code>{SERVER_IP}</code>

Используйте /start для начала работы.
"""
    
    for admin in ADMIN_ID:
        try:
            if not is_admin_notification_enabled(admin):
                continue
            await bot.send_message(admin, text, parse_mode="HTML")
        except Exception as e:
            print(f"Ошибка отправки уведомления: {e}")


@dp.callback_query(
    lambda c: c.data
    in [
        "main_menu",
        "openvpn_menu",
        "wireguard_menu",
        "server_menu",
        "clients_menu",
        "admins_menu",
    ]
)
async def handle_main_menus(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_ID:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    if callback.data == "main_menu":
        await callback.message.edit_text(
            "Главное меню:", reply_markup=create_main_menu()
        )
    elif callback.data == "openvpn_menu":
        await callback.message.edit_text(
            "Меню OpenVPN:", reply_markup=create_openvpn_menu()
        )
    elif callback.data == "server_menu":
        await callback.message.edit_text(
            "Меню сервера:", reply_markup=create_server_menu()
        )
    elif callback.data == "clients_menu":
        await callback.message.edit_text(
            "Привязки клиентов:", reply_markup=create_clients_menu()
        )
    elif callback.data == "admins_menu":
        await callback.message.edit_text(
            "Администраторы:", reply_markup=create_admins_menu()
        )
    else:
        await callback.message.edit_text(
            "Меню WireGuard:", reply_markup=create_wireguard_menu()
        )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("clientmap_"))
async def handle_clientmap_actions(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_ID:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return

    data = callback.data
    if data == "clientmap_add":
        await callback.message.edit_text(
            "Отправьте привязку в формате:\n"
            "<code>client_id:имя_клиента</code>\n"
            "Например: <code>123456789:vpn-user</code>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="clients_menu")]
                ]
            ),
        )
        await state.set_state(VPNSetup.entering_client_mapping)
        await callback.answer()
        return

    if data.startswith("clientmap_delete_confirm_"):
        telegram_id = data.split("_")[-1]
        remove_client_mapping(telegram_id)
        await callback.message.edit_text(
            "Привязка удалена.", reply_markup=create_clients_menu()
        )
        await callback.answer()
        return

    if data.startswith("clientmap_"):
        telegram_id = data.split("_", 1)[1]
        client_map = get_client_mapping()
        client_name = client_map.get(telegram_id)
        if not client_name:
            await callback.message.edit_text(
                "Привязка не найдена.", reply_markup=create_clients_menu()
            )
            await callback.answer()
            return
        await callback.message.edit_text(
            f"Удалить привязку <code>{get_user_label(telegram_id)}</code> → "
            f"<b>{client_name}</b>?",
            reply_markup=create_clientmap_delete_menu(telegram_id, client_name),
        )
        await callback.answer()
        return


@dp.callback_query(
    lambda c: c.data
    in ["notifications_menu", "toggle_notifications", "toggle_load_notifications"]
)
async def handle_notifications_menu(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_ID:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return

    if callback.data == "toggle_notifications":
        current = is_admin_notification_enabled(callback.from_user.id)
        set_admin_notification(callback.from_user.id, not current)
    elif callback.data == "toggle_load_notifications":
        current = is_admin_load_notification_enabled(callback.from_user.id)
        set_admin_load_notification(callback.from_user.id, not current)

    await callback.message.edit_text(
        "Настройка уведомлений:",
        reply_markup=create_notifications_menu(callback.from_user.id),
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "server_stats")
async def handle_server_stats(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_ID:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return

    stats_text = await get_server_stats()
    await callback.message.edit_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="server_menu")]
            ]
        ),
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "server_reboot")
async def handle_server_reboot(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_ID:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    await callback.message.edit_text(
        "⚠️ <b>Внимание!</b>\n\n"
        "Перезагрузка сервера прервет активные подключения. "
        "Подтвердите действие.",
        reply_markup=create_reboot_confirm_menu(),
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "server_reboot_confirm")
async def handle_server_reboot_confirm(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_ID:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    await callback.message.edit_text("⏳ Перезагрузка сервера...")
    try:
        await asyncio.create_subprocess_exec(
            "/sbin/shutdown", "-r", "now"
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка запуска перезагрузки:\n{e}",
            reply_markup=create_server_menu(),
        )
        return
        
    await callback.answer("")


@dp.callback_query(lambda c: c.data == "server_services")
async def handle_server_services(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_ID:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    services_text = await get_services_status_text()
    await callback.message.edit_text(
        services_text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="server_menu")]
            ]
        ),
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "server_online")
async def handle_server_online(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_ID:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    online_text = await get_online_clients_text()
    await callback.message.edit_text(
        online_text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="server_menu")]
            ]
        ),
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "server_thresholds")
async def handle_server_thresholds(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_ID:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    await callback.message.edit_text(
        "Пороги нагрузки:", reply_markup=create_thresholds_menu()
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data in ["set_cpu_threshold", "set_memory_threshold"])
async def handle_set_threshold_prompt(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_ID:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    if callback.data == "set_cpu_threshold":
        await callback.message.edit_text(
            "Введите порог CPU (1-100):",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="server_thresholds")]
                ]
            ),
        )
        await state.set_state(VPNSetup.entering_cpu_threshold)
    else:
        await callback.message.edit_text(
            "Введите порог RAM (1-100):",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="server_thresholds")]
                ]
            ),
        )
        await state.set_state(VPNSetup.entering_memory_threshold)
    await callback.answer()


@dp.message(VPNSetup.entering_cpu_threshold)
async def handle_cpu_threshold_input(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_ID:
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


@dp.message(VPNSetup.entering_memory_threshold)
async def handle_memory_threshold_input(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_ID:
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


@dp.callback_query(lambda c: c.data == "no_action")
async def handle_no_action(callback: types.CallbackQuery):
    await callback.answer(
        "В разработке", show_alert=False
    )  # Просто закрываем всплывающее окно


@dp.callback_query(lambda c: c.data.startswith("client_"))
async def handle_client_selection(callback: types.CallbackQuery, state: FSMContext):
    _, vpn_type, client_name = callback.data.split("_", 2)
    if callback.from_user.id not in ADMIN_ID:
        allowed_client = get_client_name_for_user(callback.from_user.id)
        if not allowed_client or allowed_client != client_name:
            await callback.answer("Доступ запрещен!", show_alert=True)
            return
        await state.update_data(client_mode=True)
    await state.update_data(client_name=client_name, vpn_type=vpn_type)

    back_callback = (
        "back_to_client_menu"
        if callback.from_user.id not in ADMIN_ID
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


@dp.callback_query(VPNSetup.choosing_config_type)
async def handle_interface_selection(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    client_name = user_data["client_name"]
    vpn_type = user_data["vpn_type"]
    client_mode = user_data.get("client_mode", False)

    # Обработка кнопки "Назад"
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
    if callback.from_user.id not in ADMIN_ID:
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
            pattern = re.compile(
                rf"{interface}-{re.escape(name_core)}-\([^)]+\)-{proto}\.ovpn"
            )

        matched_file = None
        if os.path.exists(dir_path):
            for file in os.listdir(dir_path):
                if pattern.fullmatch(file):
                    matched_file = os.path.join(dir_path, file)
                    break

        if matched_file and await send_single_config(
            callback.from_user.id, matched_file, os.path.basename(matched_file)
        ):
            await callback.message.delete()
            if callback.from_user.id in ADMIN_ID:
                await callback.message.answer(
                    "Главное меню:", reply_markup=create_main_menu()
                )
            else:
                await show_client_menu(callback.message, callback.from_user.id)
            await state.clear()
        else:
            await callback.answer("❌ Файл не найден", show_alert=True)

    elif callback.data.startswith("back_to_interface_"):
        await handle_back_to_interface(callback, state)


@dp.callback_query(VPNSetup.choosing_wg_type)
async def handle_wg_type_selection(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    client_name = user_data["client_name"]
    if callback.from_user.id not in ADMIN_ID:
        allowed_client = get_client_name_for_user(callback.from_user.id)
        if not allowed_client or allowed_client != client_name:
            await callback.answer("Доступ запрещен!", show_alert=True)
            await state.clear()
            return

    # Обработка кнопки "Назад"
    if callback.data.startswith("back_to_interface_"):
        await handle_back_to_interface(callback, state)
        await callback.answer()
        return

    if callback.data.startswith("send_wg_"):
        _, _, interface, wg_type, _ = callback.data.split("_", 4)

        name_core = client_name.replace("antizapret-", "").replace("vpn-", "")
        dir_path = f"/root/antizapret/client/{'wireguard' if wg_type == 'wg' else 'amneziawg'}/{interface}/"
        pattern = re.compile(
            rf"{interface}-{re.escape(name_core)}-\([^)]+\)-{wg_type}\.conf"
        )

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

        await state.update_data(
            {
                "file_path": matched_file,
                "original_name": os.path.basename(matched_file),
                "short_name": f"{name_core}-{wg_type}.conf",
            }
        )

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
        if callback.from_user.id in ADMIN_ID:
            await callback.message.answer(
                "Главное меню:", reply_markup=create_main_menu()
            )
        else:
            await show_client_menu(callback.message, callback.from_user.id)

    except Exception as e:
        print(f"Ошибка при отправке файла: {e}")
        await callback.answer("❌ Ошибка при отправке файла", show_alert=True)

    await state.clear()


async def handle_back_to_interface(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    client_name = user_data["client_name"]
    vpn_type = user_data["vpn_type"]
    back_callback = (
        "back_to_client_menu"
        if user_data.get("client_mode")
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


@dp.callback_query(lambda c: c.from_user.id in ADMIN_ID)
async def handle_callback_query(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает нажатия на кнопки в Telegram боте и выполняет соответствующие действия."""
    data = callback.data
    user_id = callback.from_user.id

    try:
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
            await send_config(message.chat.id, client_name, option)
            await message.answer("✅ Клиент создан!")
            await message.answer("Главное меню:", reply_markup=create_main_menu())
        else:
            await message.answer(f"❌ Ошибка: {result['stderr']}")
        await state.clear()


@dp.message(VPNSetup.entering_days)
async def handle_days(message: types.Message, state: FSMContext):
    """Обрабатывает ввод количества дней для создания клиента в боте."""
    update_admin_info(message.from_user)
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
    update_admin_info(message.from_user)
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
            and not c.startswith("OpenVPN client names:")  # Убираем заголовок OpenVPN
            and not c.startswith(
                "WireGuard/AmneziaWG client names:"
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
        if option == "4":  # WireGuard
            name_core = client_name.replace("antizapret-", "").replace("vpn-", "")
            directories = [
                (
                    "/root/antizapret/client/amneziawg/antizapret",
                    "AmneziaWG (antizapret)",
                ),
                ("/root/antizapret/client/amneziawg/vpn", "AmneziaWG (vpn)"),
            ]
            pattern = re.compile(
                rf"(antizapret|vpn)-{re.escape(name_core)}-\([^)]+\)-am\.conf"
            )
        else:  # OpenVPN
            directories = [
                ("/root/antizapret/client/openvpn/antizapret", "OpenVPN (antizapret)"),
                ("/root/antizapret/client/openvpn/vpn", "OpenVPN (vpn)"),
            ]
            pattern = re.compile(
                rf"(antizapret|vpn)-{re.escape(client_name)}-\([^)]+\)\.ovpn"
            )

        timeout = 25
        interval = 0.5
        files_found = []

        for directory, config_type in directories:
            try:
                for filename in os.listdir(directory):
                    if pattern.fullmatch(filename):
                        full_path = os.path.join(directory, filename)

                        # Ждём появления файла, если его ещё нет
                        elapsed = 0
                        while not os.path.exists(full_path) and elapsed < timeout:
                            await asyncio.sleep(interval)
                            elapsed += interval

                        if os.path.exists(full_path):
                            files_found.append((full_path, config_type))
                        break  # нашли один подходящий — больше не ищем в этой папке
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


# Добавляем функцию send_backup здесь
async def send_backup(chat_id: int) -> bool:
    """Функция отправки резервной копии"""

    paths_to_check = [
        f"/root/antizapret/backup-{SERVER_IP}.tar.gz",
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

    return False  # Если ни один файл не найден


def get_color_by_percent(percent):
    """Возвращает цвет в зависимости от загрузки."""
    if percent < 50:
        return "🟢"  # зеленый
    elif percent < 80:
        return "🟡"  # желтый
    else:
        return "🔴"  # красный


async def get_server_stats():
    """Получает статистику сервера."""
    try:
        
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        disk = psutil.disk_usage("/")
        disk_total = disk.total / (1024**3)
        disk_used = disk.used / (1024**3)
        uptime = format_uptime(get_uptime())
        main_interface = get_main_interface()

        if main_interface:
            stats = psutil.net_io_counters(pernic=True)[main_interface]

        file_paths = [
            ("/etc/openvpn/server/logs/antizapret-udp-status.log", "UDP"),
            ("/etc/openvpn/server/logs/antizapret-tcp-status.log", "TCP"),
            ("/etc/openvpn/server/logs/vpn-udp-status.log", "VPN-UDP"),
            ("/etc/openvpn/server/logs/vpn-tcp-status.log", "VPN-TCP"),
        ]

        vpn_clients = count_online_clients(file_paths)
        clients_section = format_vpn_clients(vpn_clients)

        stats_text = f"""
<b>📊 Статистика сервера: </b>

{get_color_by_percent(cpu_percent)} <b>ЦП:</b> {cpu_percent:>5}%
{get_color_by_percent(memory_percent)} <b>ОЗУ:</b> {memory_percent:>5}%
<b>👥 Онлайн: </b> {clients_section}
<b>💿 Диск:</b> {disk_used:.1f}/{disk_total:.1f} GB
<b>⏱️ Uptime:</b> {uptime}
<b>🌐 Трафик</b> {main_interface}: ⬇ {stats.bytes_recv / (1024**3):.2f} GB / ⬆ {stats.bytes_sent / (1024**3):.2f} GB

"""
        return stats_text
    except Exception as e:
        return f"❌ Ошибка получения статистики: {str(e)}"


async def get_service_state(service_name: str) -> str:
    try:
        process = await asyncio.create_subprocess_exec(
            "/bin/systemctl",
            "is-active",
            service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        state = stdout.decode().strip()

        if state not in ("active", "inactive", "failed"):
            return "unknown"

        return state
    except Exception:
        return "unknown"



async def get_services_status_text():
    services = [
        ("StatusOpenVPN", "StatusOpenVPN.service"),
        ("Telegram bot", "telegram-bot.service"),
    ]
    lines = ["<b>⚙️ Службы StatusOpenVPN:</b>", ""]
    for label, service in services:
        state = await get_service_state(service)
        icon = "🟢" if state == "active" else "🔴" if state == "inactive" else "🟡"
        lines.append(f"{icon} <b>{label}:</b> {state}")
    return "\n".join(lines)


def get_openvpn_online_clients():
    clients = set()
    file_paths = [
        "/etc/openvpn/server/logs/antizapret-udp-status.log",
        "/etc/openvpn/server/logs/antizapret-tcp-status.log",
        "/etc/openvpn/server/logs/vpn-udp-status.log",
        "/etc/openvpn/server/logs/vpn-tcp-status.log",
    ]
    for file_path in file_paths:
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                for line in file:
                    if not line.startswith("CLIENT_LIST"):
                        continue
                    parts = line.strip().split(",")
                    if len(parts) < 2:
                        continue
                    client_name = parts[1].strip()
                    if client_name:
                        clients.add(client_name)
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"Ошибка чтения {file_path}: {e}")
    return sorted(clients)


def parse_handshake_time(raw_value: str):
    value = (raw_value or "").strip()
    if not value:
        return None
    if value.lower() == "now":
        return datetime.datetime.now()
    if value.lower() in ["never", "n/a", "(none)"]:
        return None
    if any(
        unit in value
        for unit in [
            "мин",
            "час",
            "сек",
            "minute",
            "hour",
            "second",
            "day",
            "week",
        ]
    ):
        return parse_relative_time(value)
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def parse_wireguard_online_clients(output: str):
    online_clients = []
    lines = (output or "").splitlines()

    vpn_mapping = read_wg_config("/etc/wireguard/vpn.conf")
    antizapret_mapping = read_wg_config("/etc/wireguard/antizapret.conf")
    client_mapping = {**vpn_mapping, **antizapret_mapping}

    current_peer = None
    for line in lines:
        line = line.strip()
        if line.startswith("peer:"):
            current_peer = line.split(":", 1)[1].strip()
            continue
        if line.startswith("latest handshake:") and current_peer:
            handshake_raw = line.split(":", 1)[1].strip()
            handshake_time = parse_handshake_time(handshake_raw)
            if handshake_time and is_peer_online(handshake_time):
                online_clients.append(client_mapping.get(current_peer, current_peer))
            current_peer = None

    return sorted(set(online_clients))


async def get_wireguard_online_clients():
    try:
        process = await asyncio.create_subprocess_exec(
            "/usr/bin/wg",
            "show",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            return []
        return parse_wireguard_online_clients(stdout.decode())
    except Exception:
        return []


async def get_online_clients_text():
    openvpn_clients = get_openvpn_online_clients()
    wg_clients = await get_wireguard_online_clients()

    lines = ["<b>👥 Кто онлайн:</b>", ""]
    if openvpn_clients:
        lines.append("<b>OpenVPN:</b>")
        lines.extend([f"• {client}" for client in openvpn_clients])
    else:
        lines.append("<b>OpenVPN:</b> нет активных клиентов")
    lines.append("")
    if wg_clients:
        lines.append("<b>WireGuard:</b>")
        lines.extend([f"• {client}" for client in wg_clients])
    else:
        lines.append("<b>WireGuard:</b> нет активных клиентов")
    return "\n".join(lines)


async def monitor_server_load():
    while True:
        await asyncio.sleep(LOAD_CHECK_INTERVAL)
        if not ADMIN_ID:
            continue

        try:
            cpu_percent = await asyncio.to_thread(psutil.cpu_percent, 1)
            memory_percent = psutil.virtual_memory().percent
        except Exception as e:
            print(f"Ошибка проверки нагрузки: {e}")
            continue

        cpu_threshold, memory_threshold = get_load_thresholds()
        if (
            cpu_percent < cpu_threshold
            and memory_percent < memory_threshold
        ):
            continue

        now_ts = time.time()
        alert_text = (
            "<b>⚠️ Высокая нагрузка на сервер</b>\n\n"
            f"{get_color_by_percent(cpu_percent)} <b>ЦП:</b> {cpu_percent:>5}%\n"
            f"{get_color_by_percent(memory_percent)} <b>ОЗУ:</b> {memory_percent:>5}%"
        )
        for admin in ADMIN_ID:
            if not is_admin_notification_enabled(admin):
                continue
            if not is_admin_load_notification_enabled(admin):
                continue
            last_sent = last_load_alerts.get(admin, 0)
            if now_ts - last_sent < LOAD_ALERT_COOLDOWN:
                continue
            try:
                await bot.send_message(admin, alert_text, parse_mode="HTML")
                last_load_alerts[admin] = now_ts
            except Exception as e:
                print(f"Ошибка отправки уведомления о нагрузке: {e}")


def get_main_interface():
    """Определяет основной сетевой интерфейс системы."""

    # Сортируем интерфейсы по трафику (самый активный - первый)
    interfaces = psutil.net_io_counters(pernic=True)

    if not interfaces:
        return None

    # Ищем интерфейс с максимальным трафиком
    main_iface = max(
        interfaces.items(), key=lambda x: x[1].bytes_recv + x[1].bytes_sent
    )[0]

    return main_iface


def format_vpn_clients(clients_dict):
    """Форматирует словарь клиентов в красивую строку."""
    
    total = clients_dict['WireGuard'] + clients_dict['OpenVPN']
    
    if total == 0:
        return "0 шт."
    
    return f"""
├ <b>WireGuard:</b> {clients_dict['WireGuard']} шт.
└ <b>OpenVPN:</b> {clients_dict['OpenVPN']} шт."""


async def main():
    """Главная функция для запуска бота."""
    print("✅ Бот успешно запущен!")
    try:
        await update_bot_description()
        await notify_admin_server_online()
        await update_bot_about()
        await set_bot_commands()
        asyncio.create_task(monitor_server_load())
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
