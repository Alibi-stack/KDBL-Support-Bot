import asyncio
import logging
import re
from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from config import get_settings
from handlers.start import build_duty_text, get_callback_language, is_work_time
from handlers.user_dialog import (
    AI_UNAVAILABLE_TEXT,
    clean_ai_answer,
    safe_edit_or_answer,
    save_ai_history,
)
from keyboards.inline import (
    after_ai_keyboard,
    back_to_menu_keyboard,
    main_menu_keyboard,
    ticket_claim_keyboard,
    ticket_keyboard,
    ticket_open_keyboard,
)
from keyboards.reply import cancel_keyboard
from services.ai_client import AIServiceError, get_ai_response
from services.i18n import get_message_language, pick
from services.ticket_storage import (
    add_message,
    assign_ticket,
    close_ticket,
    create_ticket,
    get_active_ticket_by_operator,
    get_active_ticket_by_user,
    get_ticket,
    get_ticket_by_thread,
    set_ticket_admin_message,
    set_ticket_admin_thread,
)
from states.user_states import UserDialog
from utils import split_long_message

router = Router()
logger = logging.getLogger(__name__)

CANNED_RESPONSES = {
    "hello": (
        "Здравствуйте! Я оператор KDBL Support. Сейчас помогу разобраться с "
        "вашей проблемой.\n\n"
        "Сәлеметсіз бе! Мен KDBL Support операторымын. Қазір мәселеңізді "
        "шешуге көмектесемін."
    ),
    "reboot": (
        "Попробуйте, пожалуйста, полностью перезагрузить устройство и проверить "
        "проблему еще раз. Если не поможет, напишите, что изменилось.\n\n"
        "Құрылғыны толық қайта қосып, мәселені қайта тексеріп көріңіз. Егер "
        "көмектеспесе, не өзгергенін жазыңыз."
    ),
    "details": (
        "Уточните, пожалуйста: модель устройства, что именно не работает, "
        "когда началась проблема и есть ли текст ошибки или скриншот.\n\n"
        "Нақтылап жіберіңіз: құрылғы моделі, нақты не істемейді, мәселе қашан "
        "басталды және қате мәтіні немесе скриншот бар ма?"
    ),
    "done": (
        "Проверьте, пожалуйста, решилась ли проблема. Если все работает, мы "
        "закроем обращение.\n\n"
        "Мәселе шешілді ме, тексеріп жіберіңіз. Егер бәрі жұмыс істесе, өтінішті "
        "жабамыз."
    ),
}


@router.callback_query(F.data == "human_support")
async def ask_support_question(callback: CallbackQuery, state: FSMContext) -> None:
    user = callback.from_user
    if user.is_bot:
        await callback.answer()
        return

    active_ticket = await get_active_ticket_by_user(user.id)
    if active_ticket:
        await callback.message.answer(
            f"У вас уже есть открытое обращение #{active_ticket.id}. Напишите сюда "
            "новое сообщение, и я передам его оператору.\n"
            f"Сізде #{active_ticket.id} ашық өтініш бар. Жаңа хабарламаңызды "
            "осында жазыңыз, мен операторға жіберемін."
        )
        await callback.answer()
        return

    if is_after_work_hours():
        language = await get_callback_language(callback)
        await state.clear()
        await callback.message.answer(
            build_duty_text(language),
            reply_markup=main_menu_keyboard(),
        )
        await callback.answer("Сейчас вне рабочего времени")
        return

    data = await state.get_data()
    last_question = data.get("last_question")
    await state.set_state(UserDialog.waiting_support_question)

    if last_question:
        await create_support_ticket(
            callback.message,
            state,
            last_question,
            user_override=callback.from_user,
        )
        await callback.answer("Обращение создано / Өтініш құрылды")
        return

    await callback.message.answer(
        "Опишите проблему для оператора одним текстовым сообщением.\n"
        "Операторға мәселеңізді бір мәтіндік хабарламада жазыңыз.",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


def is_after_work_hours() -> bool:
    return not is_work_time()


@router.callback_query(F.data.startswith("ticket_take:"))
async def take_ticket(callback: CallbackQuery) -> None:
    ticket_id = int(callback.data.split(":", 1)[1])
    user = callback.from_user
    if user.is_bot:
        await callback.answer()
        return

    ticket = await assign_ticket(ticket_id, user.id, user.full_name)

    if ticket is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return

    ticket = await ensure_ticket_topic(callback, ticket) or ticket

    topic_url = None
    if ticket.admin_thread_id is not None:
        topic_url = build_message_url(ticket.admin_chat_id, ticket.admin_thread_id)

    if ticket.admin_thread_id is None:
        await callback.message.edit_text(
            (
                f"Обращение #{ticket.id} взято в работу\n"
                f"Оператор: {user.full_name}\n"
                "Ветка не создана: включите Topics и право бота управлять темами."
            ),
            reply_markup=ticket_claim_keyboard(ticket.id),
        )
    elif callback.message.message_thread_id == ticket.admin_thread_id:
        await callback.message.answer(
            f"Обращение #{ticket.id} взял(а) в работу: {user.full_name}.\n"
            "Теперь пишите обычные сообщения в этой ветке."
        )
    else:
        await cleanup_general_ticket_message(callback, ticket.id, topic_url)
    await callback.bot.send_message(
        ticket.user_id,
        f"Оператор взял обращение #{ticket.id} в работу.\n"
        f"Оператор #{ticket.id} өтінішін жұмысқа алды.",
    )
    await callback.answer("Взято в работу")


@router.callback_query(F.data.startswith("ticket_close:"))
async def close_ticket_callback(callback: CallbackQuery) -> None:
    ticket_id = int(callback.data.split(":", 1)[1])
    ticket = await close_ticket(ticket_id)

    if ticket is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return

    await mark_callback_message_closed(callback)
    await callback.message.answer(f"Обращение #{ticket.id} закрыто.")
    await callback.bot.send_message(
        ticket.user_id,
        f"Обращение #{ticket.id} закрыто. Спасибо!\n"
        f"#{ticket.id} өтініші жабылды. Хабарласқаныңызға рақмет!",
        reply_markup=back_to_menu_keyboard(),
    )
    await maybe_close_topic(callback)
    await callback.answer("Закрыто")


@router.callback_query(F.data.startswith("ticket_tpl:"))
async def send_canned_response(callback: CallbackQuery) -> None:
    _, ticket_id_text, template_key = callback.data.split(":", 2)
    ticket_id = int(ticket_id_text)
    response = CANNED_RESPONSES.get(template_key)

    if response is None:
        await callback.answer("Шаблон не найден", show_alert=True)
        return

    ticket = await get_ticket(ticket_id)
    if ticket is None or ticket.status == "closed":
        await callback.answer("Обращение не найдено или закрыто", show_alert=True)
        return

    operator = callback.from_user
    if operator.is_bot:
        await callback.answer()
        return

    await send_operator_text_to_user(
        bot_message=callback.message,
        ticket_id=ticket.id,
        operator_id=operator.id,
        operator_name=operator.full_name,
        text=response,
    )
    await callback.message.answer(
        f"Быстрый ответ отправлен пользователю по обращению #{ticket.id}."
    )
    await callback.answer("Отправлено")


@router.message(UserDialog.waiting_support_question, F.text)
async def handle_support_question(message: Message, state: FSMContext) -> None:
    if message.from_user and message.from_user.is_bot:
        return

    if is_after_work_hours():
        language = await get_message_language(message)
        await state.clear()
        await message.answer(
            build_duty_text(language),
            reply_markup=main_menu_keyboard(),
        )
        return

    if message.text.casefold() in {"отмена", "болдырмау"}:
        await state.clear()
        await message.answer(
            "Обращение отменено.\nӨтініш тоқтатылды.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(
            "Главное меню / Басты мәзір",
            reply_markup=main_menu_keyboard(),
        )
        return

    await create_support_ticket(message, state, message.text)


@router.message(UserDialog.waiting_support_question)
async def handle_support_non_text(message: Message) -> None:
    await message.answer(
        "Для оператора нужен текст вопроса. Напишите сообщение или нажмите Отмена.\n"
        "Операторға мәтін керек. Хабарлама жазыңыз немесе Отмена басыңыз."
    )


@router.message(F.chat.id == get_settings().admin_chat_id, F.reply_to_message)
async def handle_admin_reply(message: Message) -> None:
    settings = get_settings()
    if settings.admin_chat_id is None:
        return
    if message.from_user and message.from_user.is_bot:
        return

    ticket_id = parse_ticket_id(message.reply_to_message.text or "")
    if ticket_id is None and message.message_thread_id is not None:
        ticket = await get_ticket_by_thread(message.chat.id, message.message_thread_id)
        ticket_id = ticket.id if ticket else None

    if ticket_id is None:
        return

    await handle_operator_message(message, ticket_id)


@router.message(F.chat.id == get_settings().admin_chat_id, F.text)
async def handle_admin_topic_message(message: Message) -> None:
    settings = get_settings()
    if settings.admin_chat_id is None:
        return
    if message.from_user and message.from_user.is_bot:
        return
    if message.text and message.text.startswith("/"):
        return
    if message.reply_to_message:
        return

    ticket = None
    if message.message_thread_id is not None:
        ticket = await get_ticket_by_thread(message.chat.id, message.message_thread_id)
    if ticket is None and message.from_user is not None:
        ticket = await get_active_ticket_by_operator(message.from_user.id)
    if ticket is None:
        return

    await handle_operator_message(message, ticket.id)


@router.message(F.chat.id == get_settings().admin_chat_id, F.photo)
async def handle_admin_topic_photo(message: Message) -> None:
    settings = get_settings()
    if settings.admin_chat_id is None:
        return
    if message.from_user and message.from_user.is_bot:
        return

    ticket = None
    if message.message_thread_id is not None:
        ticket = await get_ticket_by_thread(message.chat.id, message.message_thread_id)
    if ticket is None and message.from_user is not None:
        ticket = await get_active_ticket_by_operator(message.from_user.id)
    if ticket is None:
        return

    await handle_operator_message(message, ticket.id)


@router.message(F.chat.type == "private", F.photo)
async def forward_user_photo_to_operator(message: Message) -> None:
    user = message.from_user
    if user is None or user.is_bot:
        return

    ticket = await get_active_ticket_by_user(user.id)
    if ticket is None:
        await message.answer(
            "Сначала создайте обращение оператору, потом отправьте скриншот сюда.\n"
            "Алдымен операторға өтініш ашыңыз, содан кейін скриншотты осында жіберіңіз.",
            reply_markup=main_menu_keyboard(),
        )
        return

    settings = get_settings()
    if settings.admin_chat_id is None:
        await message.answer(
            "Админ-чат пока не настроен.\n"
            "Админ-чат әлі бапталмаған.",
            reply_markup=main_menu_keyboard(),
        )
        return

    caption = message.caption or "Фото/скриншот от пользователя."
    await add_message(ticket.id, "user", user.id, user.full_name, f"[photo] {caption}")
    await send_admin_photo_message(
        message,
        ticket.id,
        (
            f"Фото от пользователя по обращению #{ticket.id}\n"
            f"TICKET_ID: {ticket.id}\n"
            f"Пользователь: {user.full_name}\n\n"
            f"{caption}"
        ),
        ticket.admin_thread_id,
    )
    await message.answer(
        "Фото передано оператору.\n"
        "Фото операторға жіберілді."
    )


@router.message(F.chat.type == "private", F.text)
async def forward_user_message_to_operator(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if user is None or user.is_bot:
        return

    ticket = await get_active_ticket_by_user(user.id)
    if ticket is None:
        # У пользователя нет открытого тикета оператору: сначала пробуем
        # ответить через RAG-пайплайн (база знаний + Grok), и только если
        # это не помогло — предлагаем создать тикет.
        await answer_with_rag(message, state)
        return

    settings = get_settings()
    if settings.admin_chat_id is None:
        await message.answer(
            "Админ-чат пока не настроен.\n"
            "Админ-чат әлі бапталмаған.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await add_message(ticket.id, "user", user.id, user.full_name, message.text)
    await send_admin_ticket_message(
        message,
        ticket.id,
        (
            f"Сообщение от пользователя по обращению #{ticket.id}\n"
            f"TICKET_ID: {ticket.id}\n"
            f"Пользователь: {user.full_name}\n\n"
            f"{message.text}"
        ),
        ticket.admin_thread_id,
    )
    await message.answer(
        "Сообщение передано оператору.\n"
        "Хабарлама операторға жіберілді."
    )


async def answer_with_rag(message: Message, state: FSMContext) -> None:
    """Отвечает пользователю через RAG-пайплайн (knowledge_base.json + Grok),
    пока у него нет открытого тикета оператору. Если AI недоступен или
    ошибся — вежливо сообщаем об этом и предлагаем создать тикет, а не
    роняем обработчик."""
    data = await state.get_data()
    history = data.get("ai_history", [])
    language = await get_message_language(message)

    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    processing_message = await message.answer(
        "Запрос обрабатывается...\n"
        "Сұраныс өңделіп жатыр..."
    )

    try:
        answer = await get_ai_response(message.text, history=history)
    except (AIServiceError, TimeoutError, asyncio.TimeoutError):
        logger.exception("AI service failed in support fallback flow")
        answer = AI_UNAVAILABLE_TEXT
    except Exception:
        logger.exception("Unexpected AI handler error in support fallback flow")
        answer = AI_UNAVAILABLE_TEXT

    answer = clean_ai_answer(answer)

    chunks = split_long_message(answer)
    await safe_edit_or_answer(processing_message, message, chunks[0])
    for chunk in chunks[1:]:
        await message.answer(chunk)

    await save_ai_history(state, history, message.text, answer)
    await message.answer(
        pick(
            language,
            "Если ответ не помог, можно создать обращение оператору или вернуться в "
            "меню.",
            "Жауап көмектеспесе, операторға өтініш ашуға немесе мәзірге оралуға "
            "болады.",
        ),
        reply_markup=after_ai_keyboard(show_duty=not is_work_time()),
    )


async def create_support_ticket(
    message: Message,
    state: FSMContext,
    question: str,
    user_override=None,
) -> None:
    settings = get_settings()

    if settings.admin_chat_id is None:
        await message.answer(
            "Админ-чат пока не настроен. Напишите /chat_id в группе операторов "
            "и вставьте полученный ID в .env.\n"
            "Админ-чат әлі бапталмаған. Операторлар тобында /chat_id жазып, "
            "шыққан ID-ді .env файлына енгізіңіз.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    user = user_override or message.from_user
    if user is not None and user.is_bot:
        return

    user_id = user.id if user else message.chat.id
    user_name = user.full_name if user else "unknown"
    username = user.username if user else None

    active_ticket = await get_active_ticket_by_user(user_id)
    if active_ticket:
        await add_message(active_ticket.id, "user", user_id, user_name, question)
        await send_admin_ticket_message(
            message,
            active_ticket.id,
            (
                f"Новое сообщение по обращению #{active_ticket.id}\n"
                f"TICKET_ID: {active_ticket.id}\n"
                f"Пользователь: {user_name}\n\n"
                f"{question}"
            ),
            active_ticket.admin_thread_id,
            full_keyboard=active_ticket.admin_thread_id is not None,
        )
        await state.clear()
        await message.answer(
            f"Сообщение добавлено в обращение #{active_ticket.id}.\n"
            f"Хабарлама #{active_ticket.id} өтінішіне қосылды.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    try:
        ticket = await create_ticket(
            user_id=user_id,
            user_name=user_name,
            username=username,
            question=question,
            admin_chat_id=settings.admin_chat_id,
        )

        admin_message = await message.bot.send_message(
            settings.admin_chat_id,
            build_general_ticket_text(
                ticket.id,
                user_id,
                user_name,
                username,
                question,
            ),
            reply_markup=ticket_claim_keyboard(ticket.id),
        )
        await set_ticket_admin_message(ticket.id, admin_message.message_id)
    except Exception:
        logger.exception("Cannot create support ticket")
        await message.answer(
            "Не удалось создать обращение. Попробуйте чуть позже.\n"
            "Өтініш құру мүмкін болмады. Кейінірек қайталап көріңіз.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await state.clear()
    await message.answer(
        f"Обращение #{ticket.id} создано. Оператор ответит в этом чате.\n"
        f"#{ticket.id} өтініші құрылды. Оператор осы чатта жауап береді.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "Главное меню / Басты мәзір",
        reply_markup=main_menu_keyboard(),
    )


async def handle_operator_message(message: Message, ticket_id: int) -> None:
    if message.from_user and message.from_user.is_bot:
        return

    operator = message.from_user
    operator_name = operator.full_name if operator else "operator"
    operator_id = operator.id if operator else message.chat.id

    if message.text:
        await send_operator_text_to_user(
            bot_message=message,
            ticket_id=ticket_id,
            operator_id=operator_id,
            operator_name=operator_name,
            text=message.text,
        )
        await message.answer("Ответ отправлен пользователю.")
        return

    if message.photo:
        await send_operator_photo_to_user(
            bot_message=message,
            ticket_id=ticket_id,
            operator_id=operator_id,
            operator_name=operator_name,
            caption=message.caption or "",
        )
        await message.answer("Фото отправлено пользователю.")
        return

    await message.answer("Пока можно отправлять пользователю текст или фото.")


async def send_admin_ticket_message(
    message: Message,
    ticket_id: int,
    text: str,
    thread_id: int | None,
    full_keyboard: bool = False,
) -> None:
    settings = get_settings()
    keyboard = ticket_keyboard(ticket_id) if full_keyboard else ticket_claim_keyboard(ticket_id)
    try:
        await message.bot.send_message(
            settings.admin_chat_id,
            text,
            reply_markup=keyboard,
            message_thread_id=thread_id,
        )
    except TelegramBadRequest:
        logger.exception("Cannot send ticket message to topic, falling back to General")
        await message.bot.send_message(
            settings.admin_chat_id,
            text,
            reply_markup=ticket_claim_keyboard(ticket_id),
        )


async def send_admin_photo_message(
    message: Message,
    ticket_id: int,
    caption: str,
    thread_id: int | None,
) -> None:
    settings = get_settings()
    if not message.photo:
        return

    photo_id = message.photo[-1].file_id
    try:
        await message.bot.send_photo(
            settings.admin_chat_id,
            photo=photo_id,
            caption=caption[:1024],
            reply_markup=ticket_keyboard(ticket_id),
            message_thread_id=thread_id,
        )
    except TelegramBadRequest:
        logger.exception("Cannot send ticket photo to topic, falling back to General")
        await message.bot.send_photo(
            settings.admin_chat_id,
            photo=photo_id,
            caption=caption[:1024],
            reply_markup=ticket_claim_keyboard(ticket_id),
        )


async def cleanup_general_ticket_message(
    callback: CallbackQuery,
    ticket_id: int,
    topic_url: str | None,
) -> None:
    try:
        await callback.message.delete()
        return
    except TelegramBadRequest:
        logger.exception("Cannot delete General ticket card, editing instead")

    await callback.message.edit_text(
        f"Обращение #{ticket_id} открыто в отдельной ветке.",
        reply_markup=ticket_open_keyboard(ticket_id, topic_url),
    )


async def mark_callback_message_closed(callback: CallbackQuery) -> None:
    message = callback.message
    if message.text:
        try:
            await message.edit_text(
                mark_ticket_closed(message.text),
                reply_markup=None,
            )
            return
        except TelegramBadRequest:
            logger.exception("Cannot edit closed ticket text")

    if message.caption:
        try:
            await message.edit_caption(
                caption=mark_ticket_closed(message.caption)[:1024],
                reply_markup=None,
            )
            return
        except TelegramBadRequest:
            logger.exception("Cannot edit closed ticket caption")

    try:
        await message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        logger.exception("Cannot remove closed ticket keyboard")


async def ensure_ticket_topic(callback: CallbackQuery, ticket) -> object | None:
    if ticket.admin_thread_id is not None:
        return ticket

    thread_id = await create_ticket_topic(
        callback.message,
        ticket.id,
        ticket.user_name,
        ticket.question,
    )
    if thread_id is None:
        return ticket

    updated_ticket = await set_ticket_admin_thread(ticket.id, thread_id)
    ticket = updated_ticket or ticket
    await callback.bot.send_message(
        chat_id=ticket.admin_chat_id,
        message_thread_id=thread_id,
        text=build_ticket_text(
            ticket.id,
            ticket.user_id,
            ticket.user_name,
            ticket.username,
            ticket.question,
            has_topic=True,
        ),
        reply_markup=ticket_keyboard(ticket.id),
    )
    return ticket


async def send_operator_text_to_user(
    bot_message: Message,
    ticket_id: int,
    operator_id: int,
    operator_name: str,
    text: str,
) -> None:
    ticket = await get_ticket(ticket_id)
    if ticket is None or ticket.status == "closed":
        await bot_message.answer("Обращение не найдено или уже закрыто.")
        return

    await add_message(ticket.id, "operator", operator_id, operator_name, text)

    if ticket.status == "open":
        ticket = await assign_ticket(ticket.id, operator_id, operator_name) or ticket

    for chunk in split_long_message(f"Оператор по обращению #{ticket.id}:\n\n{text}"):
        await bot_message.bot.send_message(ticket.user_id, chunk)


async def send_operator_photo_to_user(
    bot_message: Message,
    ticket_id: int,
    operator_id: int,
    operator_name: str,
    caption: str,
) -> None:
    ticket = await get_ticket(ticket_id)
    if ticket is None or ticket.status == "closed":
        await bot_message.answer("Обращение не найдено или уже закрыто.")
        return
    if not bot_message.photo:
        return

    await add_message(ticket.id, "operator", operator_id, operator_name, f"[photo] {caption}")

    if ticket.status == "open":
        ticket = await assign_ticket(ticket.id, operator_id, operator_name) or ticket

    user_caption = f"Оператор по обращению #{ticket.id}"
    if caption:
        user_caption = f"{user_caption}:\n\n{caption}"

    await bot_message.bot.send_photo(
        ticket.user_id,
        photo=bot_message.photo[-1].file_id,
        caption=user_caption[:1024],
    )


async def create_ticket_topic(
    message: Message,
    ticket_id: int,
    user_name: str,
    question: str,
) -> int | None:
    settings = get_settings()
    if not settings.use_forum_topics:
        return None

    topic_name = build_topic_name(ticket_id, user_name, question)
    try:
        topic = await message.bot.create_forum_topic(
            chat_id=settings.admin_chat_id,
            name=topic_name,
        )
    except TelegramBadRequest:
        logger.exception("Cannot create forum topic, using general chat fallback")
        return None

    return topic.message_thread_id


async def maybe_close_topic(callback: CallbackQuery) -> None:
    if callback.message.message_thread_id is None:
        return

    try:
        await callback.bot.close_forum_topic(
            chat_id=callback.message.chat.id,
            message_thread_id=callback.message.message_thread_id,
        )
    except TelegramBadRequest:
        logger.exception("Cannot close forum topic")


def build_ticket_text(
    ticket_id: int,
    user_id: int,
    user_name: str,
    username: str | None,
    question: str,
    has_topic: bool,
) -> str:
    username_text = f"@{username}" if username else "-"
    topic_hint = "" if has_topic else (
        "\n\nВетка не создана: включите Темы / Topics в группе и дайте боту "
        "право управлять темами."
    )
    return (
        f"Новое обращение #{ticket_id}\n"
        f"TICKET_ID: {ticket_id}\n"
        f"USER_ID: {user_id}\n"
        f"Пользователь: {user_name}\n"
        f"Username: {username_text}\n"
        "Статус: open\n\n"
        f"Вопрос:\n{question}\n\n"
        "Оператор: нажмите 'Взять в работу'. После этого пишите ответы прямо "
        "в этой теме, бот отправит их пользователю."
        f"{topic_hint}"
    )


def build_general_ticket_text(
    ticket_id: int,
    user_id: int,
    user_name: str,
    username: str | None,
    question: str,
) -> str:
    username_text = f"@{username}" if username else "-"
    short_question = re.sub(r"\s+", " ", question).strip()
    if len(short_question) > 180:
        short_question = f"{short_question[:177]}..."

    return (
        f"Новое обращение #{ticket_id}\n"
        f"TICKET_ID: {ticket_id}\n"
        f"USER_ID: {user_id}\n"
        f"Пользователь: {user_name}\n"
        f"Username: {username_text}\n"
        "Статус: open\n\n"
        f"Вопрос: {short_question}\n\n"
        "Нажмите 'Взять в работу', чтобы открыть отдельную ветку обращения."
    )


def build_message_url(chat_id: int | None, message_id: int | None) -> str | None:
    if chat_id is None or message_id is None:
        return None
    chat_id_text = str(chat_id)
    if not chat_id_text.startswith("-100"):
        return None
    internal_chat_id = chat_id_text.removeprefix("-100")
    return f"https://t.me/c/{internal_chat_id}/{message_id}"


def build_topic_name(ticket_id: int, user_name: str, question: str) -> str:
    return f"Обращение #{ticket_id}"


def parse_ticket_id(text: str) -> int | None:
    marker = "TICKET_ID:"
    if marker in text:
        try:
            return int(text.split(marker, 1)[1].splitlines()[0].strip())
        except ValueError:
            return None

    match = re.search(r"[Тт]икет\w*\s*#(\d+)", text)
    if match:
        return int(match.group(1))

    match = re.search(r"#(\d+)", text)
    if match:
        return int(match.group(1))

    return None


def mark_ticket_in_progress(text: str, operator_name: str) -> str:
    if "Статус: open" in text:
        text = text.replace("Статус: open", "Статус: in_progress", 1)
    elif "Статус: in_progress" not in text:
        text = f"{text}\nСтатус: in_progress"

    if "Оператор в работе:" not in text:
        text = f"{text}\n\nОператор в работе: {operator_name}"

    return text


def mark_ticket_closed(text: str) -> str:
    if "Статус: in_progress" in text:
        text = text.replace("Статус: in_progress", "Статус: closed", 1)
    elif "Статус: open" in text:
        text = text.replace("Статус: open", "Статус: closed", 1)
    elif "Статус: closed" not in text:
        text = f"{text}\nСтатус: closed"

    return text
