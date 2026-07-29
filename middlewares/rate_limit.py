import time
from collections import defaultdict, deque

from aiogram import BaseMiddleware
from aiogram.types import Message

from config import get_settings


class RateLimitMiddleware(BaseMiddleware):

    def __init__(self):
        self.requests = defaultdict(deque)

    async def __call__(self, handler, event: Message, data):

        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id

        settings = get_settings()

        limit = settings.rate_limit_messages
        window = settings.rate_limit_window

        now = time.time()

        history = self.requests[user_id]

        while history and history[0] <= now - window:
            history.popleft()

        if len(history) >= limit:
            await event.answer(
                "⚠️ Слишком много запросов. Подождите несколько секунд."
            )
            return

        history.append(now)

        return await handler(event, data)