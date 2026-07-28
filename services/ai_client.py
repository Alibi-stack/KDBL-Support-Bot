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

Важно: отвечай строго на проблему, которую написал пользователь. Не заменяй ее
другой проблемой. Если пользователь написал, что компьютер завис, отвечай про
зависший компьютер, а не про аккаунт, принтер или интернет.

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
        try:
            return await asyncio.wait_for(_get_gemini_response(user_text), timeout=12)
        except (AIServiceError, TimeoutError, asyncio.TimeoutError):
            logger.exception("Gemini unavailable, using local fallback")
            return await _get_local_it_fallback(user_text)

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


async def _get_local_it_fallback(user_text: str) -> str:
    lowered = user_text.lower()

    if any(
        word in lowered
        for word in ("комп", "компьютер", "завис", "зависает", "не отвечает")
    ):
        return (
            "Gemini сейчас отвечает медленно, поэтому даю базовую подсказку.\n\n"
            "1. Подождите 1-2 минуты: возможно, система завершает обновление или "
            "тяжелую задачу.\n"
            "2. Нажмите Ctrl + Alt + Delete и попробуйте открыть Диспетчер задач.\n"
            "3. Если не помогает, удерживайте кнопку питания 5-10 секунд, затем "
            "включите компьютер снова.\n"
            "4. Если проблема повторяется, создайте тикет оператору.\n\n"
            "Gemini баяу жауап беріп жатыр, сондықтан негізгі кеңес: 1-2 минут "
            "күтіңіз, Ctrl + Alt + Delete басып көріңіз, көмектеспесе компьютерді "
            "қайта қосыңыз."
        )

    if any(word in lowered for word in ("принтер", "печать", "басып")):
        return (
            "Gemini сейчас отвечает медленно, поэтому даю базовую подсказку.\n\n"
            "Проверьте питание принтера, бумагу, кабель/Wi-Fi, очередь печати и "
            "перезапустите принтер. Если не поможет, создайте тикет оператору."
        )

    return (
        "Gemini сейчас отвечает медленно. Попробуйте переформулировать вопрос "
        "или создайте тикет оператору, если проблема срочная.\n\n"
        "Gemini баяу жауап беріп жатыр. Сұрақты нақтылап жазыңыз немесе мәселе "
        "шұғыл болса, операторға тикет ашыңыз."
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
