import asyncio
import json
import logging
import re

import aiohttp
from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardRemove

from config import get_settings
from handlers.start import (
    build_duty_text,
    build_phonebook_text,
    get_callback_language,
    is_work_time,
)
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
    ticket_phonebook_keyboard,
    ticket_route_keyboard,
    ticket_transfer_keyboard,
)
from keyboards.reply import cancel_keyboard
from services import metrics
from services.ai_client import AIServiceError, get_ai_response
from services.audit import log_event
from services.i18n import get_message_language, pick
from services.operator_intent import build_operator_ticket_question, is_operator_request
from services.ticket_routing import ALLOWED_DEPARTMENTS, RoutingDecision, classify_ticket_route
from services.ticket_storage import (
    add_message,
    assign_ticket,
    close_ticket,
    create_ticket,
    get_active_ticket_by_operator,
    get_active_ticket_by_user,
    get_ticket,
    get_ticket_by_thread,
    release_ticket,
    reassign_ticket_route,
    set_ticket_admin_message,
    set_ticket_admin_thread,
)
from states.user_states import UserDialog
from utils import split_long_message

router = Router()
logger = logging.getLogger(__name__)

APP_TICKET_THREAD_CACHE: dict[int, int] = {}

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

PHONEBOOK_RESPONSES = {
    "simbase": "Номера сотрудников по Simbase:\n\n535 - Асхат\n534 - Абдулла\n474 - Олжас",
    "metadoc": "Номера сотрудников по Metadoc:\n\n700 - Дархан\n477 - Абылайхан",
    "lotus_tech": "Номера сотрудников по Lotus и техническим вопросам:\n\n700 - Дархан",
    "all": build_phonebook_text("ru"),
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


@router.callback_query(F.data.startswith("app_ticket_take:"))
async def take_app_ticket(callback: CallbackQuery) -> None:
    ticket_id = int(callback.data.split(":", 1)[1])
    user = callback.from_user
    if user.is_bot:
        await callback.answer()
        return

    remember_app_ticket_thread(callback.message, ticket_id)
    await update_mini_app_ticket_status(ticket_id, "in_progress")
    ticket_text = mark_app_ticket_status(callback.message.text or "", "in_progress")
    await callback.message.edit_text(
        ticket_text or (callback.message.text or ""),
        reply_markup=app_ticket_operator_keyboard(ticket_id, user.full_name),
    )
    await callback.message.answer(
        f"Mini App ticket #{ticket_id} is in work: {user.full_name}.\n"
        "Reply in this topic or reply to the ticket card. The answer will appear in Mini App."
    )
    await callback.answer("Taken")

@router.callback_query(F.data.startswith("app_ticket_taken:"))
async def app_ticket_already_taken(callback: CallbackQuery) -> None:
    await callback.answer("Тикет уже в работе")


@router.callback_query(F.data.startswith("app_ticket_close:"))
async def close_app_ticket(callback: CallbackQuery) -> None:
    ticket_id = int(callback.data.split(":", 1)[1])
    user = callback.from_user
    if user.is_bot:
        await callback.answer()
        return

    remember_app_ticket_thread(callback.message, ticket_id)
    await update_mini_app_ticket_status(ticket_id, "closed", user.full_name)
    ticket_text = mark_app_ticket_status(callback.message.text or "", "closed")
    await callback.message.edit_text(ticket_text or (callback.message.text or ""), reply_markup=None)
    await callback.message.answer(
        f"Mini App ticket #{ticket_id} закрыт оператором: {user.full_name}."
    )
    await callback.answer("Закрыто")


@router.callback_query(F.data.startswith("app_ticket_tpl:"))
async def send_app_ticket_canned_response(callback: CallbackQuery) -> None:
    _, ticket_id_text, template_key = callback.data.split(":", 2)
    ticket_id = int(ticket_id_text)
    response = CANNED_RESPONSES.get(template_key)
    if response is None:
        await callback.answer("Template not found", show_alert=True)
        return

    operator = callback.from_user
    if operator.is_bot:
        await callback.answer()
        return

    await bridge_operator_text_to_mini_app(callback.message, ticket_id, response)
    await callback.answer("Sent")


@router.callback_query(F.data.startswith("app_ticket_phonebook_menu:"))
async def show_app_ticket_phonebook_menu(callback: CallbackQuery) -> None:
    ticket_id = int(callback.data.split(":", 1)[1])
    await callback.message.answer(
        "Выберите, какие номера отправить в Mini App:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Simbase",
                        callback_data=f"app_ticket_phonebook:{ticket_id}:simbase",
                    ),
                    InlineKeyboardButton(
                        text="1C",
                        callback_data=f"app_ticket_phonebook:{ticket_id}:onec",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Metadoc",
                        callback_data=f"app_ticket_phonebook:{ticket_id}:metadoc",
                    ),
                    InlineKeyboardButton(
                        text="Личный кабинет",
                        callback_data=f"app_ticket_phonebook:{ticket_id}:personal_account",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Lotus / тех. вопросы",
                        callback_data=f"app_ticket_phonebook:{ticket_id}:lotus_tech",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Все номера",
                        callback_data=f"app_ticket_phonebook:{ticket_id}:all",
                    ),
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("app_ticket_route_menu:"))
async def show_app_ticket_route_menu(callback: CallbackQuery) -> None:
    ticket_id = int(callback.data.split(":", 1)[1])
    await callback.message.answer(
        f"Choose new route for Mini App ticket #{ticket_id}:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="operator", callback_data=f"app_ticket_route:{ticket_id}:operator"),
                    InlineKeyboardButton(text="developer", callback_data=f"app_ticket_route:{ticket_id}:developer"),
                ],
                [
                    InlineKeyboardButton(text="documents", callback_data=f"app_ticket_route:{ticket_id}:documents"),
                    InlineKeyboardButton(text="bot_admin", callback_data=f"app_ticket_route:{ticket_id}:bot_admin"),
                ],
                [
                    InlineKeyboardButton(text="unknown / triage", callback_data=f"app_ticket_route:{ticket_id}:unknown"),
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("app_ticket_route:"))
async def reassign_app_ticket_route(callback: CallbackQuery) -> None:
    _, ticket_id_text, department = callback.data.split(":", 2)
    ticket_id = int(ticket_id_text)
    if department not in ALLOWED_DEPARTMENTS:
        await callback.answer("Invalid route", show_alert=True)
        return
    operator = callback.from_user
    if operator.is_bot:
        await callback.answer()
        return
    ok = await update_mini_app_ticket_route(ticket_id, department, operator.full_name)
    if not ok:
        await callback.answer("Cannot update route", show_alert=True)
        return
    target_chat_id, target_thread_id = get_route_target(department)
    if target_chat_id != callback.message.chat.id or target_thread_id != callback.message.message_thread_id:
        await callback.bot.send_message(
            target_chat_id,
            f"{mark_app_ticket_route(callback.message.text or '', department)}\n\nManual route changed by: {operator.full_name}",
            reply_markup=app_ticket_operator_keyboard(ticket_id),
            message_thread_id=target_thread_id,
        )
    await callback.message.answer(
        f"Mini App ticket #{ticket_id} route changed to {department}. History saved."
    )
    await callback.answer("Route changed")


@router.callback_query(F.data.startswith("app_ticket_phonebook:"))
async def send_app_ticket_phonebook_response(callback: CallbackQuery) -> None:
    _, ticket_id_text, category = callback.data.split(":", 2)
    ticket_id = int(ticket_id_text)
    response = PHONEBOOK_RESPONSES.get(category)
    if response is None:
        await callback.answer("Category not found", show_alert=True)
        return

    operator = callback.from_user
    if operator.is_bot:
        await callback.answer()
        return

    await bridge_operator_text_to_mini_app(callback.message, ticket_id, response)
    await callback.answer("Sent")


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

    log_event(
        "ticket_assigned",
        ticket_id=ticket.id,
        operator_id=user.id,
        operator_name=user.full_name,
    )

    ticket = await ensure_ticket_topic(callback, ticket) or ticket

    topic_url = None
    if ticket.admin_thread_id is not None:
        topic_url = build_message_url(ticket.admin_chat_id, ticket.admin_thread_id)

    if ticket.admin_thread_id is None:
        await callback.message.edit_text(
            (
                f"Тикет #{ticket.id} взят в работу\n"
                f"Оператор: {user.full_name}\n"
                "Ветка не создана: включите Topics и право бота управлять темами."
            ),
            reply_markup=ticket_claim_keyboard(ticket.id),
        )
    elif callback.message.message_thread_id == ticket.admin_thread_id:
        await callback.message.answer(
            f"Тикет #{ticket.id} взял(а) в работу: {user.full_name}.\n"
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


@router.callback_query(F.data.startswith("ticket_transfer:"))
async def transfer_ticket(callback: CallbackQuery) -> None:
    ticket_id = int(callback.data.split(":", 1)[1])
    ticket = await get_ticket(ticket_id)

    if ticket is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return

    if ticket.status == "closed":
        await callback.answer("Тикет уже закрыт", show_alert=True)
        return

    previous_operator_id = ticket.operator_id
    previous_operator_name = ticket.operator_name

    ticket = await release_ticket(ticket_id)
    if ticket is None:
        await callback.answer("Не удалось передать тикет", show_alert=True)
        return

    transferred_by = callback.from_user
    log_event(
        "ticket_transferred",
        ticket_id=ticket.id,
        previous_operator_id=previous_operator_id,
        previous_operator_name=previous_operator_name,
        transferred_by_id=transferred_by.id if transferred_by else None,
        transferred_by_name=transferred_by.full_name if transferred_by else None,
    )

    try:
        keyboard = (
            ticket_keyboard(ticket.id)
            if callback.message.message_thread_id is not None
            else ticket_claim_keyboard(ticket.id)
        )
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except TelegramBadRequest:
        logger.exception("Cannot keep transferred topic keyboard")

    settings = get_settings()
    if settings.admin_chat_id is not None and callback.message.message_thread_id is not None:
        try:
            admin_message = await callback.bot.send_message(
                settings.admin_chat_id,
                build_general_ticket_text(
                    ticket.id,
                    ticket.user_id,
                    ticket.user_name,
                    ticket.username,
                    ticket.question,
                ),
                reply_markup=ticket_claim_keyboard(ticket.id),
            )
            await set_ticket_admin_message(ticket.id, admin_message.message_id)
        except TelegramBadRequest:
            logger.exception("Cannot publish transferred ticket to General")

    await callback.message.answer(
        f"Тикет #{ticket.id} передан. Карточка снова отправлена в General, другой оператор может взять его в работу."
    )
    await callback.answer("Передано")


@router.callback_query(F.data.startswith("ticket_route_menu:"))
async def show_ticket_route_menu(callback: CallbackQuery) -> None:
    ticket_id = int(callback.data.split(":", 1)[1])
    ticket = await get_ticket(ticket_id)
    if ticket is None or ticket.status == "closed":
        await callback.answer("Обращение не найдено или закрыто", show_alert=True)
        return
    await callback.message.answer(
        f"Выберите новый маршрут для тикета #{ticket.id}:",
        reply_markup=ticket_route_keyboard(ticket.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ticket_route:"))
async def reassign_ticket_department(callback: CallbackQuery) -> None:
    _, ticket_id_text, department = callback.data.split(":", 2)
    ticket_id = int(ticket_id_text)
    if department not in ALLOWED_DEPARTMENTS:
        await callback.answer("Недопустимый маршрут", show_alert=True)
        return

    actor = callback.from_user
    target_chat_id, target_thread_id = get_route_target(department)
    ticket = await reassign_ticket_route(
        ticket_id,
        department,
        actor.id if actor else None,
        actor.full_name if actor else None,
        target_chat_id,
        target_thread_id,
    )
    if ticket is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return

    await callback.message.answer(
        f"Тикет #{ticket.id} переназначен: {ticket.department}.\n"
        "Исправление сохранено в истории маршрутизации."
    )
    if target_chat_id != callback.message.chat.id or target_thread_id != callback.message.message_thread_id:
        await callback.bot.send_message(
            target_chat_id,
            build_general_ticket_text(
                ticket.id,
                ticket.user_id,
                ticket.user_name,
                ticket.username,
                ticket.question,
                routing=ticket,
            ),
            reply_markup=ticket_claim_keyboard(ticket.id),
            message_thread_id=target_thread_id,
        )
    await callback.answer("Маршрут изменен")


@router.callback_query(F.data.startswith("ticket_close:"))
async def close_ticket_callback(callback: CallbackQuery) -> None:
    ticket_id = int(callback.data.split(":", 1)[1])
    ticket_before = await get_ticket(ticket_id)
    ticket = await close_ticket(ticket_id)

    if ticket is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return

    closed_by = callback.from_user
    log_event(
        "ticket_closed",
        ticket_id=ticket.id,
        closed_by_id=closed_by.id if closed_by else None,
        closed_by_name=closed_by.full_name if closed_by else None,
        assigned_operator_id=ticket_before.operator_id if ticket_before else None,
        assigned_operator_name=ticket_before.operator_name if ticket_before else None,
    )

    deleted_callback_message = await delete_callback_message_if_general(callback)
    if not deleted_callback_message:
        await mark_callback_message_closed(callback)
    await callback.message.answer(f"Тикет #{ticket.id} закрыт.")
    await callback.bot.send_message(
        ticket.user_id,
        f"Обращение #{ticket.id} закрыто. Спасибо!\n"
        f"#{ticket.id} өтініші жабылды. Хабарласқаныңызға рақмет!",
        reply_markup=back_to_menu_keyboard(),
    )
    await maybe_close_topic(callback)
    await callback.answer("Закрыто")


@router.callback_query(F.data.startswith("ticket_phonebook_menu:"))
async def show_ticket_phonebook_menu(callback: CallbackQuery) -> None:
    ticket_id = int(callback.data.split(":", 1)[1])
    ticket = await get_ticket(ticket_id)

    if ticket is None or ticket.status == "closed":
        await callback.answer("Обращение не найдено или закрыто", show_alert=True)
        return

    await callback.message.answer(
        "Выберите, какие номера отправить пользователю:",
        reply_markup=ticket_phonebook_keyboard(ticket.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ticket_phonebook:"))
async def send_ticket_phonebook_response(callback: CallbackQuery) -> None:
    _, ticket_id_text, category = callback.data.split(":", 2)
    ticket_id = int(ticket_id_text)
    response = PHONEBOOK_RESPONSES.get(category)

    if response is None:
        await callback.answer("Категория не найдена", show_alert=True)
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
        f"Номера сотрудников отправлены пользователю по тикету #{ticket.id}."
    )
    await callback.answer("Отправлено")


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
        f"Быстрый ответ отправлен пользователю по тикету #{ticket.id}."
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

    app_ticket_id = parse_app_ticket_id(message.reply_to_message.text or "")
    if app_ticket_id is not None:
        remember_app_ticket_thread(message, app_ticket_id)
        await bridge_operator_text_to_mini_app(message, app_ticket_id, message.text or "")
        return

    if message.message_thread_id is not None:
        app_ticket_id = APP_TICKET_THREAD_CACHE.get(message.message_thread_id)
        if app_ticket_id is None:
            app_ticket_id = await find_mini_app_ticket_by_thread(message.message_thread_id)
        if app_ticket_id is not None:
            remember_app_ticket_thread(message, app_ticket_id)
            logger.info(
                "Mini App reply resolved by thread: ticket=%s chat=%s thread=%s",
                app_ticket_id,
                message.chat.id,
                message.message_thread_id,
            )
            await bridge_operator_text_to_mini_app(message, app_ticket_id, message.text or "")
            return

    app_ticket_id = parse_app_ticket_id(message.reply_to_message.caption or "")
    if app_ticket_id is not None:
        remember_app_ticket_thread(message, app_ticket_id)
        await bridge_operator_text_to_mini_app(message, app_ticket_id, message.text or "")
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

    if message.message_thread_id is not None:
        app_ticket_id = APP_TICKET_THREAD_CACHE.get(message.message_thread_id)
        if app_ticket_id is None:
            app_ticket_id = await find_mini_app_ticket_by_thread(message.message_thread_id)
        if app_ticket_id is not None:
            await bridge_operator_text_to_mini_app(message, app_ticket_id, message.text or "")
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

    if message.reply_to_message:
        app_ticket_id = parse_app_ticket_id(message.reply_to_message.text or "")
        if app_ticket_id is not None:
            caption = message.caption or "Оператор отправил фото. Фото пока видно только в Telegram-группе."
            await bridge_operator_text_to_mini_app(message, app_ticket_id, f"[Фото] {caption}")
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

    metrics.messages_total.labels(type="ticket").inc()
    caption = message.caption or "Фото/скриншот от пользователя."
    await add_message(ticket.id, "user", user.id, user.full_name, f"[photo] {caption}")
    await send_admin_photo_message(
        message,
        ticket.id,
        (
            f"Фото от пользователя по тикету #{ticket.id}\n"
            f"TICKET_ID: {ticket.id}\n"
            f"Пользователь: {user.full_name}\n\n"
            f"{caption}"
        ),
        ticket.admin_thread_id,
        transfer_keyboard=True,
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
        if is_operator_request(message.text):
            data = await state.get_data()
            question = build_operator_ticket_question(
                message.text,
                data.get("last_question"),
            )
            await create_support_ticket(message, state, question)
            return

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

    metrics.messages_total.labels(type="ticket").inc()
    await add_message(ticket.id, "user", user.id, user.full_name, message.text)
    await send_admin_ticket_message(
        message,
        ticket.id,
        (
            f"Сообщение от пользователя по тикету #{ticket.id}\n"
            f"TICKET_ID: {ticket.id}\n"
            f"Пользователь: {user.full_name}\n\n"
            f"{message.text}"
        ),
        ticket.admin_thread_id,
        transfer_keyboard=True,
    )
    await message.answer(
        "Сообщение передано оператору.\n"
        "Хабарлама операторға жіберілді."
    )


@router.message()
async def handle_mini_app_topic_text_fallback(message: Message) -> None:
    if message.chat.type not in {"group", "supergroup"}:
        return
    if message.from_user and message.from_user.is_bot:
        return
    if not message.text:
        return
    if message.text and message.text.startswith("/"):
        return

    if message.reply_to_message:
        app_ticket_id = parse_app_ticket_id(message.reply_to_message.text or "")
        if app_ticket_id is not None:
            remember_app_ticket_thread(message, app_ticket_id)
            await bridge_operator_text_to_mini_app(message, app_ticket_id, message.text or "")
            return
        ticket_id = parse_ticket_id(message.reply_to_message.text or "")
        if ticket_id is not None:
            await handle_operator_message(message, ticket_id)
            return

    if message.message_thread_id is None:
        logger.info("Group text ignored: chat=%s has no thread id", message.chat.id)
        return

    app_ticket_id = APP_TICKET_THREAD_CACHE.get(message.message_thread_id)
    if app_ticket_id is None:
        app_ticket_id = await find_mini_app_ticket_by_thread(message.message_thread_id)
    if app_ticket_id is None:
        ticket = await get_ticket_by_thread(message.chat.id, message.message_thread_id)
        if ticket is not None:
            await handle_operator_message(message, ticket.id)
            return
        logger.info("Group topic text ignored: chat=%s thread=%s has no ticket", message.chat.id, message.message_thread_id)
        return

    remember_app_ticket_thread(message, app_ticket_id)
    await bridge_operator_text_to_mini_app(message, app_ticket_id, message.text or "")


async def answer_with_rag(message: Message, state: FSMContext) -> None:
    """Отвечает пользователю через RAG-пайплайн (knowledge_base.json + Grok),
    пока у него нет открытого тикета оператору. Если AI недоступен или
    ошибся — вежливо сообщаем об этом и предлагаем создать тикет, а не
    роняем обработчик."""
    metrics.messages_total.labels(type="ai").inc()
    data = await state.get_data()
    history = data.get("ai_history", [])
    language = await get_message_language(message)

    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    processing_message = await message.answer(
        "Запрос обрабатывается...\n"
        "Сұраныс өңделіп жатыр..."
    )

    try:
        answer = await get_ai_response(message.text, history=history, language=language)
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
    notify_user: bool = True,
) -> None:
    metrics.messages_total.labels(type="ticket").inc()
    settings = get_settings()

    if settings.admin_chat_id is None:
        if not notify_user:
            return
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
                f"Новое сообщение по тикету #{active_ticket.id}\n"
                f"TICKET_ID: {active_ticket.id}\n"
                f"Пользователь: {user_name}\n\n"
                f"{question}"
            ),
            active_ticket.admin_thread_id,
            transfer_keyboard=True,
        )
        await state.clear()
        if not notify_user:
            return
        await message.answer(
            f"Сообщение добавлено в обращение #{active_ticket.id}.\n"
            f"Хабарлама #{active_ticket.id} өтінішіне қосылды.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    try:
        routing = await classify_ticket_route(question)
        target_chat_id, target_thread_id = get_route_target(routing.department)
        ticket = await create_ticket(
            user_id=user_id,
            user_name=user_name,
            username=username,
            question=question,
            admin_chat_id=target_chat_id,
            department=routing.department,
            routing_status=routing.routing_status,
            routing_confidence=routing.confidence,
            routing_reason=routing.reason,
            clarification_question=routing.clarification_question,
            initial_department=routing.initial_department,
            final_department=routing.final_department,
            llm_model=routing.llm_model,
            routing_duration_ms=routing.duration_ms,
            routing_success=routing.success,
            routing_error_type=routing.error_type,
        )

        admin_message = await message.bot.send_message(
            target_chat_id,
            build_general_ticket_text(
                ticket.id,
                user_id,
                user_name,
                username,
                question,
                routing=routing,
            ),
            reply_markup=ticket_claim_keyboard(ticket.id),
            message_thread_id=target_thread_id,
        )
        await set_ticket_admin_message(ticket.id, admin_message.message_id)
        log_event(
            "ticket_created",
            ticket_id=ticket.id,
            user_id=user_id,
            user_name=user_name,
            username=username,
        )
    except Exception:
        logger.exception("Cannot create support ticket")
        if not notify_user:
            return
        await message.answer(
            "Не удалось создать обращение. Попробуйте чуть позже.\n"
            "Өтініш құру мүмкін болмады. Кейінірек қайталап көріңіз.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await state.clear()
    if not notify_user:
        return
    await message.answer(
        f"Обращение #{ticket.id} создано. Оператор ответит в этом чате.\n"
        f"#{ticket.id} өтініші құрылды. Оператор осы чатта жауап береді.",
        reply_markup=ReplyKeyboardRemove(),
    )
    if ticket.routing_status == "needs_clarification" and ticket.clarification_question:
        await message.answer(ticket.clarification_question)


async def handle_operator_message(message: Message, ticket_id: int) -> None:
    if message.from_user and message.from_user.is_bot:
        return

    operator = message.from_user
    operator_name = operator.full_name if operator else "operator"
    operator_id = operator.id if operator else message.chat.id

    log_event(
        "operator_message",
        ticket_id=ticket_id,
        operator_id=operator_id,
        operator_name=operator_name,
        message_type="photo" if message.photo else "text",
    )

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


async def bridge_operator_text_to_mini_app(
    message: Message,
    app_ticket_id: int,
    text: str,
) -> None:
    settings = get_settings()
    if not settings.mini_app_api_url or not settings.mini_app_api_secret:
        await message.answer("Mini App API bridge is not configured.")
        return

    text = text.strip()
    if not text:
        await message.answer("Для Mini App пока можно отправлять текстовый ответ.")
        return

    operator = message.from_user
    operator_name = operator.full_name if operator else "Оператор"
    try:
        await post_mini_app_operator_message(
            settings.mini_app_api_url,
            settings.mini_app_api_secret,
            app_ticket_id,
            operator_name,
            text,
        )
    except Exception:
        logger.exception("Cannot bridge operator reply to Mini App")
        await message.answer("Не удалось отправить ответ в Mini App.")
        return

    await message.answer("Ответ отправлен в Mini App.")


async def find_mini_app_ticket_by_thread(thread_id: int) -> int | None:
    settings = get_settings()
    if not settings.mini_app_api_url or not settings.mini_app_api_secret:
        return None

    base_url = settings.mini_app_api_url.rstrip("/")
    url = f"{base_url}/api/app-ticket-by-thread?threadId={thread_id}"

    try:
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                url,
                headers={"X-KDBL-Secret": settings.mini_app_api_secret},
            ) as response:
                if response.status >= 400:
                    logger.warning("Mini App thread lookup failed: %s", response.status)
                    return None
                data = await response.json()
                ticket_id = data.get("ticketId")
                return int(ticket_id) if ticket_id else None
    except Exception:
        logger.exception("Cannot resolve Mini App ticket by thread")
        return None


async def update_mini_app_ticket_status(
    ticket_id: int,
    status: str,
    operator_name: str | None = None,
) -> None:
    settings = get_settings()
    if not settings.mini_app_api_url or not settings.mini_app_api_secret:
        return

    base_url = settings.mini_app_api_url.rstrip("/")
    url = f"{base_url}/api/tickets/{ticket_id}/status"

    try:
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url,
                json={"status": status, "operatorName": operator_name or ""},
                headers={"X-KDBL-Secret": settings.mini_app_api_secret},
            ) as response:
                if response.status >= 400:
                    raise RuntimeError(f"Mini App status API failed with status {response.status}")
    except Exception:
        logger.exception("Cannot update Mini App ticket status")


async def update_mini_app_ticket_route(
    ticket_id: int,
    department: str,
    operator_name: str,
) -> bool:
    settings = get_settings()
    if not settings.mini_app_api_url or not settings.mini_app_api_secret:
        return False

    base_url = settings.mini_app_api_url.rstrip("/")
    url = f"{base_url}/api/tickets/{ticket_id}/route"

    try:
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url,
                json={
                    "department": department,
                    "operatorName": operator_name,
                    "reason": "Manual reassignment by operator.",
                },
                headers={"X-KDBL-Secret": settings.mini_app_api_secret},
            ) as response:
                if response.status >= 400:
                    logger.warning("Mini App route API failed: %s", response.status)
                    return False
                return True
    except Exception:
        logger.exception("Cannot update Mini App ticket route")
        return False


async def post_mini_app_operator_message(
    api_url: str,
    api_secret: str,
    ticket_id: int,
    operator_name: str,
    text: str,
) -> None:
    base_url = api_url.rstrip("/")
    url = f"{base_url}/api/tickets/{ticket_id}/messages"
    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            url,
            json={
                "operatorName": operator_name,
                "text": text,
            },
            headers={"X-KDBL-Secret": api_secret},
        ) as response:
            if response.status >= 400:
                error_text = await response.text()
                logger.warning(
                    "Mini App API message bridge failed: ticket=%s status=%s body=%s",
                    ticket_id,
                    response.status,
                    error_text[:300],
                )
                raise RuntimeError(f"Mini App API failed with status {response.status}")


async def send_admin_ticket_message(
    message: Message,
    ticket_id: int,
    text: str,
    thread_id: int | None,
    full_keyboard: bool = False,
    transfer_keyboard: bool = False,
) -> None:
    settings = get_settings()
    ticket = await get_ticket(ticket_id)
    target_chat_id = ticket.admin_chat_id if ticket and ticket.admin_chat_id is not None else settings.admin_chat_id
    if target_chat_id is None:
        return
    if transfer_keyboard:
        keyboard = ticket_transfer_keyboard(ticket_id)
    elif full_keyboard:
        keyboard = ticket_keyboard(ticket_id)
    else:
        keyboard = ticket_claim_keyboard(ticket_id)
    try:
        await message.bot.send_message(
            target_chat_id,
            text,
            reply_markup=keyboard,
            message_thread_id=thread_id,
        )
    except TelegramBadRequest:
        logger.exception("Cannot send ticket message to topic, falling back to General")
        await message.bot.send_message(
            target_chat_id,
            text,
            reply_markup=keyboard,
        )


async def send_admin_photo_message(
    message: Message,
    ticket_id: int,
    caption: str,
    thread_id: int | None,
    transfer_keyboard: bool = False,
) -> None:
    settings = get_settings()
    ticket = await get_ticket(ticket_id)
    target_chat_id = ticket.admin_chat_id if ticket and ticket.admin_chat_id is not None else settings.admin_chat_id
    if target_chat_id is None:
        return
    if not message.photo:
        return

    photo_id = message.photo[-1].file_id
    keyboard = ticket_transfer_keyboard(ticket_id) if transfer_keyboard else ticket_keyboard(ticket_id)
    try:
        await message.bot.send_photo(
            target_chat_id,
            photo=photo_id,
            caption=caption[:1024],
            reply_markup=keyboard,
            message_thread_id=thread_id,
        )
    except TelegramBadRequest:
        logger.exception("Cannot send ticket photo to topic, falling back to General")
        await message.bot.send_photo(
            target_chat_id,
            photo=photo_id,
            caption=caption[:1024],
            reply_markup=keyboard,
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
        f"Тикет #{ticket_id} открыт в отдельной ветке.",
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


async def delete_callback_message_if_general(callback: CallbackQuery) -> bool:
    if callback.message.message_thread_id is not None:
        return False

    try:
        await callback.message.delete()
        return True
    except TelegramBadRequest:
        logger.exception("Cannot delete closed General ticket card")
        return False


async def ensure_ticket_topic(callback: CallbackQuery, ticket) -> object | None:
    if ticket.admin_thread_id is not None:
        return ticket

    thread_id = await create_ticket_topic(
        callback.message,
        ticket.id,
        ticket.user_name,
        ticket.question,
        ticket.admin_chat_id,
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
        await bot_message.answer("Тикет не найден или уже закрыт.")
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
        await bot_message.answer("Тикет не найден или уже закрыт.")
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
    chat_id: int | None = None,
) -> int | None:
    settings = get_settings()
    if not settings.use_forum_topics:
        return None
    target_chat_id = chat_id or settings.admin_chat_id
    if target_chat_id is None:
        return None

    topic_name = build_topic_name(ticket_id, user_name, question)
    try:
        topic = await message.bot.create_forum_topic(
            chat_id=target_chat_id,
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
    routing: RoutingDecision | object | None = None,
) -> str:
    username_text = f"@{username}" if username else "-"
    topic_hint = "" if has_topic else (
        "\n\nВетка не создана: включите Темы / Topics в группе и дайте боту "
        "право управлять темами."
    )
    routing_text = build_routing_text(routing)
    return (
        f"Новый тикет #{ticket_id}\n"
        f"TICKET_ID: {ticket_id}\n"
        f"USER_ID: {user_id}\n"
        f"Пользователь: {user_name}\n"
        f"Username: {username_text}\n"
        "Статус: open\n\n"
        f"{routing_text}"
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
    routing: RoutingDecision | object | None = None,
) -> str:
    username_text = f"@{username}" if username else "-"
    short_question = re.sub(r"\s+", " ", question).strip()
    if len(short_question) > 180:
        short_question = f"{short_question[:177]}..."

    routing_text = build_routing_text(routing)
    return (
        f"Новый тикет #{ticket_id}\n"
        f"TICKET_ID: {ticket_id}\n"
        f"USER_ID: {user_id}\n"
        f"Пользователь: {user_name}\n"
        f"Username: {username_text}\n"
        "Статус: open\n\n"
        f"{routing_text}"
        f"Вопрос: {short_question}\n\n"
        "Нажмите 'Взять в работу', чтобы открыть отдельную ветку тикета."
    )


def build_routing_text(routing: RoutingDecision | object | None) -> str:
    if routing is None:
        return ""
    department = getattr(routing, "department", None) or "unknown"
    status = getattr(routing, "routing_status", None) or "needs_review"
    confidence = getattr(routing, "confidence", None)
    if confidence is None:
        confidence = getattr(routing, "routing_confidence", None)
    reason = getattr(routing, "reason", None) or getattr(routing, "routing_reason", None)
    question = getattr(routing, "clarification_question", None)
    warning = "Route check advised.\n" if status == "auto_routed" and (confidence or 0) < 85 else ""
    lines = [
        f"Route: {department}",
        f"Routing status: {status}",
        f"Confidence: {confidence if confidence is not None else '-'}",
    ]
    if reason:
        lines.append(f"Reason: {reason}")
    if question:
        lines.append(f"Clarification: {question}")
    if warning:
        lines.append(warning.strip())
    return "\n".join(lines) + "\n\n"


def get_route_target(department: str) -> tuple[int, int | None]:
    settings = get_settings()
    chat_map = {
        "operator": settings.operator_chat_id,
        "developer": settings.developer_chat_id,
        "documents": settings.documents_chat_id,
        "bot_admin": settings.bot_admin_chat_id,
        "unknown": settings.triage_chat_id,
    }
    thread_map = {
        "operator": settings.operator_thread_id,
        "developer": settings.developer_thread_id,
        "documents": settings.documents_thread_id,
        "bot_admin": settings.bot_admin_thread_id,
        "unknown": settings.triage_thread_id,
    }
    chat_id = chat_map.get(department) or settings.triage_chat_id or settings.admin_chat_id
    if chat_id is None:
        raise RuntimeError("No Telegram route chat is configured")
    return chat_id, thread_map.get(department)


def build_message_url(chat_id: int | None, message_id: int | None) -> str | None:
    if chat_id is None or message_id is None:
        return None
    chat_id_text = str(chat_id)
    if not chat_id_text.startswith("-100"):
        return None
    internal_chat_id = chat_id_text.removeprefix("-100")
    return f"https://t.me/c/{internal_chat_id}/{message_id}"


def build_topic_name(ticket_id: int, user_name: str, question: str) -> str:
    return f"Ticket #{ticket_id}"


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


def parse_app_ticket_id(text: str) -> int | None:
    marker = "APP_TICKET_ID:"
    if marker in text:
        try:
            return int(text.split(marker, 1)[1].splitlines()[0].strip())
        except ValueError:
            return None

    match = re.search(r"(?:New\s+)?Mini App ticket\s*#(\d+)", text, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))

    return None


def app_ticket_operator_keyboard(ticket_id: int, operator_name: str | None = None) -> InlineKeyboardMarkup:
    first_button = InlineKeyboardButton(
        text=f"In work: {(operator_name or 'operator')[:30]}",
        callback_data=f"app_ticket_taken:{ticket_id}",
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                first_button,
                InlineKeyboardButton(text="Close", callback_data=f"app_ticket_close:{ticket_id}"),
            ],
            [
                InlineKeyboardButton(text="Приветствие", callback_data=f"app_ticket_tpl:{ticket_id}:hello"),
                InlineKeyboardButton(text="Перезагрузка", callback_data=f"app_ticket_tpl:{ticket_id}:reboot"),
            ],
            [
                InlineKeyboardButton(text="Уточнить данные", callback_data=f"app_ticket_tpl:{ticket_id}:details"),
                InlineKeyboardButton(text="Закрывающий ответ", callback_data=f"app_ticket_tpl:{ticket_id}:done"),
            ],
            [
                InlineKeyboardButton(
                    text="Номера сотрудников",
                    callback_data=f"app_ticket_phonebook_menu:{ticket_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Route",
                    callback_data=f"app_ticket_route_menu:{ticket_id}",
                ),
            ],
        ]
    )


def remember_app_ticket_thread(message: Message | None, ticket_id: int) -> None:
    if message is None or message.message_thread_id is None:
        return
    APP_TICKET_THREAD_CACHE[message.message_thread_id] = ticket_id


def mark_app_ticket_status(text: str, status: str) -> str:
    if not text:
        return text
    if re.search(r"^Status:\s*\w+", text, flags=re.MULTILINE):
        return re.sub(r"^Status:\s*\w+", f"Status: {status}", text, count=1, flags=re.MULTILINE)
    return f"{text}\nStatus: {status}"


def mark_app_ticket_route(text: str, department: str) -> str:
    if not text:
        return f"Route: {department}"
    if re.search(r"^Route:\s*\w+", text, flags=re.MULTILINE):
        return re.sub(r"^Route:\s*\w+", f"Route: {department}", text, count=1, flags=re.MULTILINE)
    return f"{text}\nRoute: {department}"


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

