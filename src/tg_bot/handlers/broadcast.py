"""Рассылка сообщений привязанным клиентам Telegram-бота."""

import asyncio
import html

from aiogram import Router, types
from aiogram.enums import ContentType
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext

from ..audit import log_action
from ..config import get_admin_ids, get_client_mapping
from ..keyboards import (
    create_broadcast_confirmation_keyboard,
    create_broadcast_input_keyboard,
    create_clients_menu,
    get_clients_menu_text,
)
from ..states import Broadcast

router = Router()

_BROADCAST_CONTENT_TYPES = {
    ContentType.TEXT,
    ContentType.PHOTO,
    ContentType.VIDEO,
    ContentType.ANIMATION,
    ContentType.AUDIO,
    ContentType.DOCUMENT,
    ContentType.VOICE,
    ContentType.VIDEO_NOTE,
    ContentType.STICKER,
}
_VPN_CONFIG_EXTENSIONS = (".ovpn", ".conf")


def get_broadcast_recipient_ids() -> list[int]:
    """Вернуть уникальные Telegram ID только из привязок клиентов."""
    return sorted(
        {
            int(telegram_id)
            for telegram_id in get_client_mapping()
            if str(telegram_id).isdigit()
        }
    )


def is_vpn_config_filename(filename: str) -> bool:
    """Распознать VPN-конфиг по имени файла без учёта регистра."""
    return (filename or "").strip().lower().endswith(_VPN_CONFIG_EXTENSIONS)


async def _show_clients_menu(message: types.Message) -> None:
    mapping = get_client_mapping()
    total_users = len(mapping)
    total_bindings = sum(len(names) for names in mapping.values())
    await message.edit_text(
        get_clients_menu_text(total_users, 1, total_bindings),
        reply_markup=create_clients_menu(get_admin_ids(), 1),
    )


@router.callback_query(lambda callback: callback.data == "broadcast_start")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in get_admin_ids():
        await callback.answer("Доступ запрещён!", show_alert=True)
        return

    recipient_count = len(get_broadcast_recipient_ids())
    if not recipient_count:
        await callback.answer("Нет привязанных клиентов.", show_alert=True)
        return

    await state.clear()
    await state.set_state(Broadcast.entering_message)
    await callback.message.edit_text(
        "📣 <b>Рассылка клиентам</b>\n\n"
        "Отправьте текст или одно сообщение с вложением. "
        "Форматирование и подпись будут сохранены.\n\n"
        f"Получателей: <b>{recipient_count}</b>.",
        reply_markup=create_broadcast_input_keyboard(),
    )
    await callback.answer()


@router.message(Broadcast.entering_message)
async def prepare_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id not in get_admin_ids():
        await state.clear()
        return

    if message.content_type not in _BROADCAST_CONTENT_TYPES:
        await message.answer(
            "Этот тип сообщения нельзя разослать. "
            "Отправьте текст, фото, видео, аудио или документ.",
            reply_markup=create_broadcast_input_keyboard(),
        )
        return
    if message.media_group_id:
        await message.answer(
            "Альбомы не поддерживаются. Отправьте одно вложение отдельным сообщением.",
            reply_markup=create_broadcast_input_keyboard(),
        )
        return

    recipient_count = len(get_broadcast_recipient_ids())
    if not recipient_count:
        await state.clear()
        await message.answer("Нет привязанных клиентов.")
        return

    document_name = ""
    if message.document and message.document.file_name:
        document_name = message.document.file_name.strip()
    config_warning = is_vpn_config_filename(document_name)

    await state.update_data(
        broadcast_source_chat_id=message.chat.id,
        broadcast_source_message_id=message.message_id,
        broadcast_config_warning=config_warning,
    )
    confirmation_text = (
        "⚠️ <b>Внимание: VPN-конфиг</b>\n\n"
        f"Файл <code>{html.escape(document_name)}</code> будет отправлен в одинаковом виде "
        f"всем <b>{recipient_count}</b> получателям. Убедитесь, что файл не "
        "содержит персональные ключи одного клиента."
        if config_warning
        else (
            "Проверьте сообщение выше.\n\n"
            f"Оно будет отправлено <b>{recipient_count}</b> "
            "привязанным клиентам."
        )
    )
    await message.answer(
        confirmation_text,
        reply_markup=create_broadcast_confirmation_keyboard(config_warning),
    )


@router.callback_query(lambda callback: callback.data == "broadcast_cancel")
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in get_admin_ids():
        await callback.answer("Доступ запрещён!", show_alert=True)
        return

    await state.clear()
    await _show_clients_menu(callback.message)
    await callback.answer("Рассылка отменена.")


@router.callback_query(lambda callback: callback.data == "broadcast_confirm")
async def confirm_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in get_admin_ids():
        await callback.answer("Доступ запрещён!", show_alert=True)
        return

    state_data = await state.get_data()
    source_chat_id = state_data.get("broadcast_source_chat_id")
    source_message_id = state_data.get("broadcast_source_message_id")
    if not source_chat_id or not source_message_id:
        await state.clear()
        await callback.answer("Сообщение для рассылки не найдено.", show_alert=True)
        return

    # Очищаем FSM до отправки, чтобы повторное нажатие не запустило
    # ту же рассылку ещё раз.
    await state.clear()
    recipient_ids = get_broadcast_recipient_ids()
    if not recipient_ids:
        await callback.message.edit_text("Нет привязанных клиентов.")
        await callback.answer()
        return

    await callback.answer("Рассылка запущена.")
    await callback.message.edit_text(
        f"⏳ Отправляю сообщение {len(recipient_ids)} клиентам…"
    )

    bot = callback.bot
    delivered = 0
    blocked = 0
    failed = 0
    for recipient_id in recipient_ids:
        try:
            await bot.copy_message(
                chat_id=recipient_id,
                from_chat_id=source_chat_id,
                message_id=source_message_id,
            )
            delivered += 1
        except TelegramRetryAfter as error:
            await asyncio.sleep(error.retry_after)
            try:
                await bot.copy_message(
                    chat_id=recipient_id,
                    from_chat_id=source_chat_id,
                    message_id=source_message_id,
                )
                delivered += 1
            except TelegramForbiddenError:
                blocked += 1
            except Exception as retry_error:
                print(f"Ошибка рассылки для {recipient_id}: {retry_error}")
                failed += 1
        except TelegramForbiddenError:
            blocked += 1
        except Exception as error:
            print(f"Ошибка рассылки для {recipient_id}: {error}")
            failed += 1

        # Не создаём всплеск запросов к Telegram API.
        await asyncio.sleep(0.05)

    total = len(recipient_ids)
    log_action(
        "bot",
        callback.from_user.id,
        callback.from_user.full_name,
        "client_broadcast",
        f"всего={total}, доставлено={delivered}, "
        f"бот_заблокирован={blocked}, ошибки={failed}",
    )
    await callback.message.edit_text(
        "✅ <b>Рассылка завершена</b>\n\n"
        f"Получателей: <b>{total}</b>\n"
        f"Доставлено: <b>{delivered}</b>\n"
        f"Бот заблокирован: <b>{blocked}</b>\n"
        f"Ошибки: <b>{failed}</b>",
        reply_markup=create_clients_menu(get_admin_ids(), 1),
    )
