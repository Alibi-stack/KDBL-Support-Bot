from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.inline import main_menu_keyboard

router = Router()

WELCOME_TEXT = (
    "Здравствуйте! Я KDBL Support, AI-бот IT-поддержки.\n"
    "Сәлеметсіз бе! Мен KDBL Support, IT-қолдау AI-ботымын.\n\n"
    "Опишите проблему, задайте вопрос AI или создайте тикет для оператора.\n"
    "Мәселені сипаттаңыз, AI-ға сұрақ қойыңыз немесе операторға тикет ашыңыз."
)

FAQ_TEXT = (
    "FAQ\n\n"
    "FAQ будет добавлен позже.\n"
    "FAQ кейін қосылады.\n\n"
    "Пока можно задать текстовый вопрос AI или обратиться к оператору.\n"
    "Әзірге AI-ға мәтіндік сұрақ қойып немесе операторға жүгіне аласыз."
)


@router.message(CommandStart())
async def command_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())


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
            "Темы включены. Новые тикеты должны создаваться отдельными ветками."
        )
        return

    await message.answer(
        "Темы в этой группе не включены. Поэтому тикеты падают в General.\n\n"
        "Чтобы были отдельные ветки: настройки группы -> Темы / Topics -> включить. "
        "Боту также нужно право управлять темами."
    )


@router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "faq")
async def show_faq(callback: CallbackQuery) -> None:
    await callback.message.edit_text(FAQ_TEXT, reply_markup=main_menu_keyboard())
    await callback.answer()
