from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from services.ticket_storage import (
    get_moderation_state,
    set_moderation_state,
)

BAD_WORD_RE = re.compile(
    r"\b("
    r"бля(?:ть|д)?|сука|хуй|хуе|хуё|пизд|еба|ёба|ебл|ёбл|мразь|"
    r"нахуй|похуй|заеб|долбоеб|долбоёб"
    r")\w*\b",
    re.IGNORECASE,
)

MUTE_MINUTES = 30
MAX_WARNINGS = 2


class ModerationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.text or event.from_user is None:
            return await handler(event, data)
        if event.from_user.is_bot:
            return await handler(event, data)
        if event.chat.type != "private":
            return await handler(event, data)
        if event.text.startswith("/"):
            return await handler(event, data)

        warnings, muted_until_text = await get_moderation_state(event.from_user.id)
        now = datetime.now(UTC)

        if muted_until_text:
            muted_until = datetime.fromisoformat(muted_until_text)
            if muted_until > now:
                minutes_left = max(1, int((muted_until - now).total_seconds() // 60))
                await event.answer(
                    f"Вы временно ограничены из-за грубой лексики. "
                    f"Осталось примерно {minutes_left} мин.\n"
                    f"Дөрекі сөздер үшін уақытша шектеу қойылды. "
                    f"Шамамен {minutes_left} мин қалды."
                )
                return None

        if not BAD_WORD_RE.search(event.text):
            return await handler(event, data)

        warnings += 1
        if warnings <= MAX_WARNINGS:
            await set_moderation_state(event.from_user.id, warnings, None)
            await event.answer(
                f"Предупреждение {warnings}/{MAX_WARNINGS}: пожалуйста, без "
                "матерных слов. После предупреждений будет мут на 30 минут.\n"
                f"Ескерту {warnings}/{MAX_WARNINGS}: дөрекі сөз қолданбаңыз. "
                "Ескертулерден кейін 30 минутқа шектеу қойылады."
            )
            return None

        muted_until = now + timedelta(minutes=MUTE_MINUTES)
        await set_moderation_state(
            event.from_user.id,
            0,
            muted_until.isoformat(timespec="seconds"),
        )
        await event.answer(
            "Вы получили мут на 30 минут за матерные слова.\n"
            "Дөрекі сөздер үшін 30 минутқа шектеу қойылды."
        )
        return None
