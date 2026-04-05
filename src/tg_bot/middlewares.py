"""Промежуточные слои диспетчера Telegram-бота."""

from typing import Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from .admin import is_any_admin_request_notification_enabled
from .config import get_admin_ids, is_user_allowed_for_bot, is_user_banned


def _callback_from_event(event: TelegramObject) -> Optional[CallbackQuery]:
    """В outer_middleware aiogram передаёт Update, не CallbackQuery."""
    if isinstance(event, Update):
        return event.callback_query
    if isinstance(event, CallbackQuery):
        return event
    return None


def _message_with_text_from_event(event: TelegramObject) -> Optional[Message]:
    if isinstance(event, Update):
        msg = event.message or event.edited_message
        if msg and msg.text:
            return msg
        return None
    if isinstance(event, Message) and event.text:
        return event
    return None


def _is_request_flow_event(event: TelegramObject) -> bool:
    """Команды /start, /request, /id или кнопка «Запросить доступ» — сценарий запроса доступа."""
    cq = _callback_from_event(event)
    if cq and cq.data == "request_access":
        return True
    msg = _message_with_text_from_event(event)
    if not msg or not msg.text:
        return False
    text = msg.text.strip()
    if text.startswith("/"):
        cmd = text.split()[0].split("@")[0].lower()
        if cmd in ("/start", "/request", "/id"):
            return True
    return False


class BannedUserMiddleware(BaseMiddleware):
    """Не передаёт обновления заблокированным пользователям (кроме администраторов)."""

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)
        if user.id in get_admin_ids():
            return await handler(event, data)
        if is_user_banned(user.id):
            cq = _callback_from_event(event)
            if cq:
                try:
                    await cq.answer()
                except Exception:
                    pass
            return None
        return await handler(event, data)


class UnlistedUserSilenceMiddleware(BaseMiddleware):
    """Не передаёт обновления пользователям вне списков админов и клиентов (при настроенных админах), без ответов — как бан.

    Если уведомления о запросах включены хотя бы у одного админа — для таких пользователей
    обрабатываются только /start, /request, /id и callback «Запросить доступ».
    """

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)
        if is_user_allowed_for_bot(user.id):
            return await handler(event, data)
        if is_any_admin_request_notification_enabled() and _is_request_flow_event(event):
            return await handler(event, data)
        cq = _callback_from_event(event)
        if cq:
            try:
                await cq.answer()
            except Exception:
                pass
        return None
