import asyncio
import logging
import re

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from keyboards.inline import after_ai_keyboard, main_menu_keyboard
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
    await state.update_data(ai_history=[])
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
    data = await state.get_data()
    history = data.get("ai_history", [])
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    processing_message = await message.answer(
        "Запрос обрабатывается...\n"
        "Сұраныс өңделіп жатыр...",
        reply_markup=ReplyKeyboardRemove(),
    )

    try:
        answer = await get_ai_response(message.text, history=history)
    except (AIServiceError, TimeoutError, asyncio.TimeoutError):
        logger.exception("AI service failed")
        await safe_edit_or_answer(processing_message, message, AI_UNAVAILABLE_TEXT)
        return
    except Exception:
        logger.exception("Unexpected AI handler error")
        await safe_edit_or_answer(processing_message, message, AI_UNAVAILABLE_TEXT)
        return

    answer = clean_ai_answer(answer)

    chunks = split_long_message(answer)
    await safe_edit_or_answer(processing_message, message, chunks[0])
    for chunk in chunks[1:]:
        await message.answer(chunk)

    await save_ai_history(state, history, message.text, answer)
    await state.set_state(UserDialog.waiting_question)
    await message.answer(
        "Можете сразу написать следующий вопрос. Если ответ AI не помог, "
        "создайте тикет оператору.\n"
        "Келесі сұрақты бірден жаза аласыз. AI жауабы көмектеспесе, "
        "операторға тикет ашыңыз.",
        reply_markup=after_ai_keyboard(),
    )


@router.message(UserDialog.waiting_question)
async def handle_non_text_question(message: Message) -> None:
    await message.answer(
        "Пока я понимаю только текстовые вопросы. Напишите вопрос сообщением "
        "или нажмите Отмена.\n"
        "Әзірге тек мәтіндік сұрақтарды түсінемін. Сұрақ жазыңыз немесе "
        "Отмена басыңыз."
    )


async def save_ai_history(
    state: FSMContext,
    history: list[dict[str, str]],
    user_text: str,
    ai_text: str,
) -> None:
    updated_history = [
        *history,
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": ai_text},
    ][-8:]
    await state.update_data(last_question=user_text, ai_history=updated_history)


async def safe_edit_or_answer(
    processing_message: Message,
    original_message: Message,
    text: str,
) -> None:
    try:
        await processing_message.edit_text(text)
    except TelegramBadRequest:
        logger.exception("Cannot edit processing message, sending text separately")
        await original_message.answer(text)


def clean_ai_answer(answer: str) -> str:
    cleaned_lines = [
        line for line in answer.splitlines()
        if line.strip().upper() != "NEED_HUMAN"
    ]
    cleaned = "\n".join(cleaned_lines).strip()
    if cleaned.upper().startswith("NEED_HUMAN:"):
        cleaned = cleaned.split(":", 1)[1].strip()
    cleaned = re.sub(
        r"(?i)\s*Похоже,\s*(?:у вас возникли проблемы с чем-то, но\s*)?"
        r"вы не указали[^.?!]*[.?!]\s*",
        " ",
        cleaned,
    ).strip()
    return cleaned or "Готов помочь. Напишите вопрос чуть подробнее."
