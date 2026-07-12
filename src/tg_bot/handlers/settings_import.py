"""Импорт settings.json через отправку файла администратором."""

import io
import json

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from ..audit import log_action
from ..config import get_admin_ids, load_settings, normalize_settings_data, save_settings
from ..keyboards import create_main_menu, create_settings_import_keyboard
from ..settings_report import (
    build_settings_import_message,
    settings_are_equal,
    truncate_telegram_text,
)
from ..states import VPNSetup
from ..utils import get_external_ip

router = Router()

SETTINGS_IMPORT_MAX_BYTES = 1_000_000
SETTINGS_FILE_NAME = "settings.json"
PENDING_SETTINGS_KEY = "pending_settings_import"
SETTINGS_KEY_TYPES = {
    "app_name": str,
    "telegram_admins": dict,
    "telegram_clients": dict,
    "tg_bot_banned_user_ids": list,
    "tg_bot_pending_requests": dict,
    "bot_enabled": bool,
    "show_ovpn_menu": bool,
    "show_wg_menu": bool,
    "hide_ovpn_ip": bool,
    "hide_wg_ip": bool,
    "hide_wg_warp_interface": bool,
    "shorten_wg_filenames": bool,
    "stats_retention_days": int,
    "history_max_records": int,
    "load_thresholds": dict,
    "vpn_service_monitoring_enabled": bool,
    "vpn_monitored_services": dict,
    "tg_bot_profile_seeded": bool,
}


def _is_json_document(message: types.Message) -> bool:
    document = message.document
    if not document or not document.file_name:
        return False
    return document.file_name.strip().lower().endswith(".json")


def _has_settings_structure(data: dict) -> bool:
    return any(
        key in data and isinstance(data.get(key), expected_type)
        for key, expected_type in SETTINGS_KEY_TYPES.items()
    )


@router.message(F.document)
async def handle_settings_document(message: types.Message, state: FSMContext):
    if message.from_user.id not in get_admin_ids():
        return
    if not _is_json_document(message):
        return

    document = message.document
    if document.file_size and document.file_size > SETTINGS_IMPORT_MAX_BYTES:
        await message.answer("❌ Файл слишком большой (максимум 1 МБ).")
        return

    await message.answer("⏳ Обрабатываю settings.json…")

    from ..bot import get_bot

    bot = get_bot()
    buffer = io.BytesIO()
    try:
        await bot.download(document, buffer)
        raw = buffer.getvalue().decode("utf-8")
        parsed = json.loads(raw)
    except UnicodeDecodeError:
        await message.answer("❌ Файл должен быть в кодировке UTF-8.")
        return
    except json.JSONDecodeError:
        await message.answer("❌ Некорректный JSON в settings.json.")
        return
    except Exception:
        await message.answer("❌ Не удалось скачать или прочитать файл.")
        return

    if not isinstance(parsed, dict):
        await message.answer("❌ Корневой элемент settings.json должен быть объектом JSON.")
        return
    if not _has_settings_structure(parsed):
        await message.answer("❌ Структура файла не похожа на settings.json.")
        return

    imported = normalize_settings_data(parsed)
    current = normalize_settings_data(load_settings())
    equal = settings_are_equal(current, imported)
    text = truncate_telegram_text(
        build_settings_import_message(current, imported, equal=equal)
    )

    if equal:
        await state.clear()
        await message.answer(text)
        return

    await state.update_data(**{PENDING_SETTINGS_KEY: json.dumps(imported, ensure_ascii=False)})
    await state.set_state(VPNSetup.confirming_settings_import)
    await message.answer(text, reply_markup=create_settings_import_keyboard())


@router.callback_query(
    lambda c: c.data in ("settings_import_confirm", "settings_import_cancel")
)
async def handle_settings_import_callback(
    callback: types.CallbackQuery,
    state: FSMContext,
):
    if callback.from_user.id not in get_admin_ids():
        await callback.answer("Доступ запрещен!", show_alert=True)
        return

    if callback.data == "settings_import_cancel":
        await state.clear()
        await callback.message.edit_text("❌ Замена настроек отменена.")
        await callback.answer()
        return

    data = await state.get_data()
    raw = data.get(PENDING_SETTINGS_KEY)
    if not raw:
        await state.clear()
        await callback.answer("Сессия истекла. Отправьте файл снова.", show_alert=True)
        return

    try:
        imported = normalize_settings_data(json.loads(raw))
    except json.JSONDecodeError:
        await state.clear()
        await callback.answer("Сессия повреждена. Отправьте файл снова.", show_alert=True)
        return

    save_settings(imported)
    await state.clear()

    report = truncate_telegram_text(
        build_settings_import_message(imported, imported, equal=True, replaced=True)
    )
    server_ip = get_external_ip()
    await callback.message.edit_text(
        report,
        reply_markup=create_main_menu(server_ip),
    )
    await callback.answer("Настройки сохранены")
    log_action(
        "bot",
        callback.from_user.id,
        callback.from_user.full_name,
        "settings_import",
        SETTINGS_FILE_NAME,
    )
