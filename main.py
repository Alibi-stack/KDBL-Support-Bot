import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage

from config import get_settings
from handlers import setup_routers
from services.ticket_storage import init_db


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = get_settings()
    await init_db()
    asyncio.create_task(warmup_rag())

    session = AiohttpSession(timeout=45)
    bot = Bot(token=settings.bot_token, session=session)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(setup_routers())

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
