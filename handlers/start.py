from datetime import datetime, time
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile
from aiogram.types import CallbackQuery, Message

from config import get_settings
from keyboards.inline import back_to_menu_keyboard, language_keyboard, main_menu_keyboard
from services.reports import build_daily_ticket_report
from services.ticket_storage import get_user_language, set_user_language

router = Router()

WELCOME_TEXTS = {
    "ru": (
        "Здравствуйте! Я KDBL Support, AI-ассистент. Готов помочь.\n\n"
        "Задайте вопрос AI. Если понадобится помощь человека, можно создать "
        "обращение оператору."
    ),
    "kz": (
        "Сәлеметсіз бе! Мен KDBL Support AI-ассистентімін. Көмектесуге дайынмын.\n\n"
        "AI-ға сұрақ қойыңыз. Қажет болса, операторға өтініш ашуға болады."
    ),
}

FAQ_TEXTS = {
    "ru": (
        "FAQ\n\n"
        "FAQ будет добавлен позже.\n\n"
        "Пока можно задать вопрос AI. После ответа AI можно создать обращение оператору."
    ),
    "kz": (
        "FAQ\n\n"
        "FAQ кейін қосылады.\n\n"
        "Әзірге AI-ға сұрақ қоюға болады. AI жауабынан кейін операторға өтініш "
        "ашуға болады."
    ),
}

LANGUAGE_PROMPT = (
    "Выберите язык / Тілді таңдаңыз"
)


@router.message(CommandStart())
async def command_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    language = await get_user_language(message.from_user.id)
    if language is None:
        await message.answer(LANGUAGE_PROMPT, reply_markup=language_keyboard())
        return
    await message.answer(get_welcome_text(language), reply_markup=main_menu_keyboard())


@router.message(Command("chat_id"))
async def command_chat_id(message: Message) -> None:
    title = message.chat.title or message.chat.full_name or "this chat"
    await message.answer(
        f"Chat: {title}\n"
        f"ADMIN_CHAT_ID={message.chat.id}"
    )


@router.message(Command("forum_status"))
async def command_forum_status(message: Message) -> None:
    chat = await message.bot.get_chat(message.chat.id)
    is_forum = getattr(chat, "is_forum", False)
    if is_forum:
        await message.answer(
            "Темы включены. Новые обращения должны создаваться отдельными ветками."
        )
        return

    await message.answer(
        "Темы в этой группе не включены. Поэтому обращения падают в General.\n\n"
        "Чтобы были отдельные ветки: настройки группы -> Темы / Topics -> включить. "
        "Боту также нужно право управлять темами."
    )


@router.message(Command("daily_report"))
async def command_daily_report(message: Message) -> None:
    settings = get_settings()
    if settings.admin_chat_id is None or message.chat.id != settings.admin_chat_id:
        return

    report_date = datetime.now(ZoneInfo(settings.timezone)).date()
    report_path = await build_daily_ticket_report(report_date)
    await message.answer_document(
        FSInputFile(report_path),
        caption=f"Отчёт по обращениям за {report_date:%d.%m.%Y}",
    )


@router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    language = await get_callback_language(callback)
    await callback.message.edit_text(
        get_welcome_text(language),
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "faq")
async def show_faq(callback: CallbackQuery) -> None:
    language = await get_callback_language(callback)
    await callback.message.edit_text(
        FAQ_TEXTS.get(language, FAQ_TEXTS["ru"]),
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lang:"))
async def choose_language(callback: CallbackQuery) -> None:
    language = callback.data.split(":", 1)[1]
    if language not in {"ru", "kz"}:
        await callback.answer()
        return
    await set_user_language(callback.from_user.id, language)
    await callback.message.edit_text(
        get_welcome_text(language),
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer("Сохранено")


@router.callback_query(F.data == "change_language")
async def change_language(callback: CallbackQuery) -> None:
    await callback.message.edit_text(LANGUAGE_PROMPT, reply_markup=language_keyboard())
    await callback.answer()


@router.callback_query(F.data == "phonebook")
async def show_phonebook(callback: CallbackQuery) -> None:
    language = await get_callback_language(callback)
    await callback.message.edit_text(
        build_phonebook_text(language),
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "duty_contact")
async def show_duty_contact(callback: CallbackQuery) -> None:
    language = await get_callback_language(callback)
    await callback.message.edit_text(
        build_duty_text(language),
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


async def get_callback_language(callback: CallbackQuery) -> str:
    language = await get_user_language(callback.from_user.id)
    return language or "ru"


def get_welcome_text(language: str | None) -> str:
    return WELCOME_TEXTS.get(language or "ru", WELCOME_TEXTS["ru"])


def build_phonebook_text(language: str) -> str:
    if language == "kz":
        return (
            "Операторлар нөмірлерінің анықтамалығы:\n\n"
            "700 - Дархан (Lotus, Metadoc, техникалық сұрақтар)\n"
            "535 - Асхат (Simbase)\n"
            "534 - Абдулла (Simbase)\n"
            "474 - Олжас (Simbase)\n"
            "477 - Абылайхан (Metadoc)"
        )
    return (
        "Справочник номеров операторов:\n\n"
        "700 - Дархан (Lotus, Metadoc, технические вопросы)\n"
        "535 - Асхат (Simbase)\n"
        "534 - Абдулла (Simbase)\n"
        "474 - Олжас (Simbase)\n"
        "477 - Абылайхан (Metadoc)"
    )


def build_duty_text(language: str) -> str:
    settings = get_settings()
    now = datetime.now(ZoneInfo(settings.timezone))
    after_hours = not is_work_time(now)

    if settings.duty_contact:
        if language == "kz":
            return (
                f"Жұмыс уақытынан кейін кезекші байланысы: {settings.duty_contact}"
            )
        return f"После рабочего времени дежурный контакт: {settings.duty_contact}"

    if language == "kz":
        prefix = "Қазір жұмыс уақытынан кейін." if after_hours else "Кезекші байланысы."
        return (
            f"{prefix} Кезекші оператордың username/телефоны әзірге қосылмаған."
        )

    prefix = "Сейчас вне рабочего времени." if after_hours else "Контакт дежурного."
    return (
        f"{prefix} Username или телефон дежурного пока не добавлен."
    )


def is_work_time(now: datetime | None = None) -> bool:
    settings = get_settings()
    current = now or datetime.now(ZoneInfo(settings.timezone))
    start = time(settings.workday_start_hour, settings.workday_start_minute)
    end = time(settings.workday_end_hour, 0)
    return start <= current.time() < end
