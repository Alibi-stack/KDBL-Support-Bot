import json
import logging
from types import SimpleNamespace

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from handlers.start import build_duty_text, build_phonebook_text
from keyboards.inline import main_menu_keyboard
from services.ticket_storage import get_user_language, set_user_language

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.web_app_data)
async def handle_mini_app_data(message: Message, state: FSMContext) -> None:
    if message.from_user and message.from_user.is_bot:
        return

    try:
        payload = json.loads(message.web_app_data.data)
    except (TypeError, json.JSONDecodeError):
        logger.warning("Invalid Mini App payload: %r", message.web_app_data.data)
        return

    user_id = message.from_user.id if message.from_user else message.chat.id
    action = payload.get("action")
    language = payload.get("language") or await get_user_language(user_id) or "ru"

    if action == "set_language":
        selected_language = payload.get("language")
        if selected_language in {"ru", "kz"}:
            await set_user_language(user_id, selected_language)
        return

    if action == "ask_ai":
        logger.info("Ignoring legacy Mini App ask_ai sendData event")
        return

    if action == "create_ticket":
        from handlers.support import create_support_ticket

        question = normalize_text(payload.get("question"))
        category = normalize_text(payload.get("category"))
        priority = normalize_text(payload.get("priority"))
        profile = normalize_profile(payload.get("profile"))

        details = []
        if category:
            details.append(f"Категория: {category}")
        if priority:
            details.append(f"Приоритет: {priority}")

        profile_text = build_profile_text(profile)
        if profile_text:
            details.append(profile_text)
        details.append(question)

        await create_support_ticket(
            message,
            state,
            "\n".join(item for item in details if item),
            user_override=build_profile_user(message, profile),
            notify_user=False,
        )
        return

    if action == "phonebook":
        await message.answer(build_phonebook_text(language), reply_markup=main_menu_keyboard())
        return

    if action == "duty_contact":
        await message.answer(build_duty_text(language), reply_markup=main_menu_keyboard())
        return

    logger.info("Unsupported Mini App action: %r", action)


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def normalize_profile(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        "first_name": normalize_text(value.get("firstName"))[:80],
        "last_name": normalize_text(value.get("lastName"))[:80],
        "department": normalize_text(value.get("department"))[:120],
    }


def build_profile_user(message: Message, profile: dict[str, str]) -> SimpleNamespace | None:
    telegram_user = message.from_user
    if telegram_user is None:
        return None

    profile_name = " ".join(
        item for item in (profile.get("first_name"), profile.get("last_name")) if item
    ).strip()
    return SimpleNamespace(
        id=telegram_user.id,
        full_name=profile_name or telegram_user.full_name,
        username=telegram_user.username,
        is_bot=False,
    )


def build_profile_text(profile: dict[str, str]) -> str:
    lines = []
    name = " ".join(
        item for item in (profile.get("first_name"), profile.get("last_name")) if item
    ).strip()
    if name:
        lines.append(f"Заявитель: {name}")
    if profile.get("department"):
        lines.append(f"Отдел/кабинет: {profile['department']}")
    return "\n".join(lines)
