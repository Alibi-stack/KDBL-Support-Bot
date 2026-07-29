import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage
from pythonjsonlogger.json import JsonFormatter

from config import get_settings
from handlers import setup_routers
from middlewares.moderation import ModerationMiddleware
from middlewares.rate_limit import RateLimitMiddleware
from services.metrics import start_metrics_server
from services.reports import daily_report_loop
from services.ticket_storage import init_db


def configure_logging() -> None:
    """Структурное (JSON) логирование в stdout для docker logs / агрегаторов.

    Поля timestamp/level/logger/message есть всегда; user_id/ticket_id и
    другие произвольные поля попадают в JSON автоматически, если их
    передать через logger.info(..., extra={"user_id": ...})."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger",
            },
        )
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)


async def main() -> None:
    configure_logging()

    settings = get_settings()
    start_metrics_server(8080)
    await init_db()
    asyncio.create_task(warmup_rag())

    session = AiohttpSession(timeout=45)
    bot = Bot(token=settings.bot_token, session=session)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.message.middleware(RateLimitMiddleware())
    dispatcher.message.middleware(ModerationMiddleware())
    dispatcher.include_router(setup_routers())
    asyncio.create_task(daily_report_loop(bot))

    while True:
        try:
            logging.info("Checking Telegram connection...")
            me = await asyncio.wait_for(bot.get_me(), timeout=60)
            logging.info("Telegram connection OK: @%s", me.username)
            await dispatcher.start_polling(bot)
        except (TelegramNetworkError, TimeoutError, asyncio.TimeoutError, OSError):
            logging.exception("Telegram connection problem, retrying in 5 seconds")
            await asyncio.sleep(5)


async def warmup_rag() -> None:
    try:
        import rag_engine

        logging.info("Warming up RAG index...")
        await asyncio.to_thread(rag_engine.retrieve_relevant_faq, "принтер", 1)
        logging.info("RAG index is ready")
    except Exception:
        logging.exception("RAG warmup failed; bot will use fallback retrieval")


if __name__ == "__main__":
    asyncio.run(main())
