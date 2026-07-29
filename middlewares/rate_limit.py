import time
from collections import defaultdict, deque

from aiogram import BaseMiddleware
from aiogram.types import Message

from config import get_settings


class RateLimitMiddleware(BaseMiddleware):

    def __init__(self):
        self.requests = defaultdict(deque)
        self.blocked_until = defaultdict(float)
        self.last_warning_at = defaultdict(float)

    async def __call__(self, handler, event: Message, data):

        if not isinstance(event, Message) or event.from_user is None:
            return await handler(event, data)

        user_id = event.from_user.id

        settings = get_settings()

        limit = settings.rate_limit_messages
        window = settings.rate_limit_window
        cooldown = settings.rate_limit_cooldown

        now = time.time()

        if self.blocked_until[user_id] > now:
            if now - self.last_warning_at[user_id] >= 5:
                seconds_left = max(1, int(self.blocked_until[user_id] - now))
                self.last_warning_at[user_id] = now
                await event.answer(
                    f"⚠️ Слишком много запросов. Подождите {seconds_left} сек."
                )
            return

        history = self.requests[user_id]

        while history and history[0] <= now - window:
            history.popleft()

        if len(history) >= limit:
            self.blocked_until[user_id] = now + cooldown
            self.last_warning_at[user_id] = now
            history.clear()
            await event.answer(
                f"⚠️ Слишком много запросов. Пауза на {cooldown} сек."
            )
            return

        history.append(now)

        return await handler(event, data)
