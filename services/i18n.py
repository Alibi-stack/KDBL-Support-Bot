from __future__ import annotations

from aiogram.types import Message

from services.ticket_storage import get_user_language


async def get_message_language(message: Message) -> str:
    if message.from_user is None:
        return "ru"
    return await get_user_language(message.from_user.id) or "ru"


def pick(language: str | None, ru: str, kz: str) -> str:
    return kz if language == "kz" else ru
