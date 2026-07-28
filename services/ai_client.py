import asyncio
import logging

from config import get_settings

logger = logging.getLogger(__name__)


class AIServiceError(RuntimeError):
    """Raised when the AI service cannot return a valid response."""


SYSTEM_PROMPT = """
Ты AI-помощник KDBL Support для IT-поддержки.

Отвечай кратко, понятно и дружелюбно на русском языке. Если уместно, добавь
короткую казахскую версию после русского ответа. Помогай с типовыми IT-проблемами:
принтеры, интернет, вход в аккаунт, почта, компьютер, программы, доступы.

Если вопрос опасный, требует прав администратора, физического ремонта, доступа к
личным данным или ты не уверен в решении, в конце ответа напиши:
NEED_HUMAN
""".strip()


async def get_ai_response(user_text: str) -> str:
    if not user_text.strip():
        raise AIServiceError("Empty user request")

    settings = get_settings()
    provider = settings.ai_provider.lower()

    if provider == "gemini" and settings.gemini_api_key:
        return await _get_gemini_response(user_text)

    return await _get_stub_response(user_text)


async def _get_stub_response(user_text: str) -> str:
    await asyncio.sleep(0.5)

    lowered = user_text.lower()
    if "оператор" in lowered or "человек" in lowered:
        return (
            "NEED_HUMAN: Лучше подключить оператора для точного ответа.\n"
            "Дәл жауап үшін операторды қосқан дұрыс."
        )

    return (
        "Тестовый ответ AI-модуля. Сейчас можно подключить Gemini через "
        "GEMINI_API_KEY в .env.\n\n"
        f"Ваш вопрос: {user_text}"
    )


async def _get_gemini_response(user_text: str) -> str:
    try:
        return await asyncio.to_thread(_generate_gemini_text, user_text)
    except Exception as error:
        logger.exception("Gemini API request failed")
        raise AIServiceError("Gemini API request failed") from error


def _generate_gemini_text(user_text: str) -> str:
    from google import genai

    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=f"{SYSTEM_PROMPT}\n\nВопрос пользователя:\n{user_text}",
    )

    text = getattr(response, "text", None)
    if not text:
        raise AIServiceError("Gemini returned an empty response")

    return text.strip()
