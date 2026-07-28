import asyncio
import logging

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from config import get_settings
from keyboards.inline import human_support_keyboard, main_menu_keyboard
from keyboards.reply import cancel_keyboard
from services.ai_client import AIServiceError, get_ai_response
from states.user_states import UserDialog
from utils import split_long_message

router = Router()
logger = logging.getLogger(__name__)

AI_UNAVAILABLE_TEXT = (
    "Извините, сервис временно недоступен. Попробуйте чуть позже.\n"
    "Кешіріңіз, сервис уақытша қолжетімсіз. Кейінірек қайталап көріңіз."
)


@router.callback_query(F.data == "ask_ai")
async def ask_ai(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserDialog.waiting_question)
    await callback.message.answer(
        "Напишите ваш вопрос одним сообщением.\n"
        "Сұрағыңызды бір хабарламада жазыңыз.",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(F.text.casefold() == "отмена")
async def cancel_dialog(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Диалог отменен. Выберите действие в меню.\n"
        "Диалог тоқтатылды. Мәзірден әрекет таңдаңыз.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Главное меню / Басты мәзір", reply_markup=main_menu_keyboard())


@router.message(UserDialog.waiting_question, F.text)
async def handle_ai_question(message: Message, state: FSMContext) -> None:
    settings = get_settings()
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    processing_message = await message.answer(
        "Запрос обрабатывается...\n"
        "Сұраныс өңделіп жатыр...",
        reply_markup=ReplyKeyboardRemove(),
    )

    try:
        answer = await asyncio.wait_for(
            get_ai_response(message.text),
            timeout=settings.ai_request_timeout,
        )
    except (AIServiceError, TimeoutError, asyncio.TimeoutError):
        logger.exception("AI service failed")
        await processing_message.edit_text(AI_UNAVAILABLE_TEXT)
        return
    except Exception:
        logger.exception("Unexpected AI handler error")
        await processing_message.edit_text(AI_UNAVAILABLE_TEXT)
        return

    await state.clear()

    if answer.strip().startswith("NEED_HUMAN"):
        clean_answer = answer.split(":", 1)[-1].strip()
        await processing_message.edit_text(
            clean_answer
            or (
                "Для этого вопроса лучше подключить оператора.\n"
                "Бұл сұраққа операторды қосқан дұрыс."
            ),
            reply_markup=human_support_keyboard(),
        )
        await state.update_data(last_question=message.text)
        return

    chunks = split_long_message(answer)
    try:
        await processing_message.edit_text(chunks[0])
    except TelegramBadRequest:
        logger.exception("Cannot edit processing message, sending AI answer separately")
        await message.answer(chunks[0])
    for chunk in chunks[1:]:
        await message.answer(chunk)

    await message.answer("Что дальше? / Әрі қарай?", reply_markup=main_menu_keyboard())


@router.message(UserDialog.waiting_question)
async def handle_non_text_question(message: Message) -> None:
    await message.answer(
        "Пока я понимаю только текстовые вопросы. Напишите вопрос сообщением "
        "или нажмите Отмена.\n"
        "Әзірге тек мәтіндік сұрақтарды түсінемін. Сұрақ жазыңыз немесе "
        "Отмена басыңыз."
    )
