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
принтеры, интернет, вход в аккаунт, почта, компьютер, программы, доступы,
рабочие приложения и корпоративные системы: Lotus, 1C/1С, Office, браузер,
VPN, ЭЦП, порталы и внутренние сервисы.

Важно: отвечай строго на проблему, которую написал пользователь. Не заменяй ее
другой проблемой. Если пользователь написал, что компьютер завис, отвечай про
зависший компьютер, а не про аккаунт, принтер или интернет.

Учитывай историю диалога. Если пользователь пишет "альтернативы", "не помогло",
"та же задача", "еще варианты", "перечисли их", понимай это как продолжение
предыдущей IT-проблемы.

Если вопрос касается рабочей программы или корпоративной системы, считай это
IT/helpdesk-вопросом. Если пользователь спрашивает "как пользоваться Lotus" или
"как пользоваться 1С", дай базовые шаги и попроси уточнить конкретную операцию:
вход, поиск документа, подпись, отправка, ошибка, доступ.

Если вопрос совсем не относится к IT/helpdesk/техподдержке/рабочим сервисам,
вежливо скажи, что помогаешь только с IT-поддержкой, и предложи задать IT-вопрос.

Если вопрос опасный, требует прав администратора, физического ремонта, доступа к
личным данным или ты не уверен в решении, в конце ответа напиши:
NEED_HUMAN
""".strip()


async def get_ai_response(
    user_text: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    if not user_text.strip():
        raise AIServiceError("Empty user request")

    settings = get_settings()
    provider = settings.ai_provider.lower()

    if provider == "gemini" and settings.gemini_api_key:
        try:
            return await asyncio.wait_for(
                _get_gemini_response(user_text, history or []),
                timeout=12,
            )
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
            "Я KDBL Support. Вот что можно попробовать:\n\n"
            "1. Подождите 1-2 минуты: возможно, система завершает обновление или "
            "тяжелую задачу.\n"
            "2. Нажмите Ctrl + Alt + Delete и попробуйте открыть Диспетчер задач.\n"
            "3. Если не помогает, удерживайте кнопку питания 5-10 секунд, затем "
            "включите компьютер снова.\n"
            "4. Если проблема повторяется, создайте тикет оператору.\n\n"
            "KDBL Support кеңесі: 1-2 минут күтіңіз, Ctrl + Alt + Delete басып "
            "көріңіз, көмектеспесе компьютерді қайта қосыңыз."
        )

    if any(word in lowered for word in ("принтер", "печать", "басып")):
        return (
            "Я KDBL Support. Вот что можно проверить:\n\n"
            "Проверьте питание принтера, бумагу, кабель/Wi-Fi, очередь печати и "
            "перезапустите принтер. Если не поможет, создайте тикет оператору."
        )

    if any(
        word in lowered
        for word in ("lotus", "1c", "1с", "office", "excel", "word", "эцп", "vpn")
    ):
        return (
            "Я KDBL Support. Это рабочая программа, поэтому помогу.\n\n"
            "Уточните, пожалуйста, что именно нужно сделать в программе: войти, "
            "найти документ, подписать, отправить, настроить доступ или исправить "
            "ошибку. Если есть текст ошибки или скриншот, отправьте его.\n\n"
            "Мен KDBL Supportпын. Бұл жұмыс бағдарламасы, көмектесемін. Нақты "
            "қандай әрекет керек екенін жазыңыз: кіру, құжат табу, қол қою, "
            "жіберу, қолжетімділік немесе қате."
        )

    return (
        "Я KDBL Support и помогаю только с IT-вопросами: компьютер, интернет, "
        "принтер, доступы, почта, программы, Lotus, 1С и рабочие сервисы.\n\n"
        "Задайте, пожалуйста, вопрос по IT-поддержке. Если проблема срочная, "
        "можно создать тикет оператору.\n\n"
        "Мен KDBL Supportпын және тек IT сұрақтарына көмектесемін: компьютер, "
        "интернет, принтер, қолжетімділік, пошта, Lotus, 1С, бағдарламалар "
        "және жұмыс сервистері."
    )


async def _get_gemini_response(
    user_text: str,
    history: list[dict[str, str]],
) -> str:
    try:
        return await asyncio.to_thread(_generate_gemini_text, user_text, history)
    except Exception as error:
        logger.exception("Gemini API request failed")
        raise AIServiceError("Gemini API request failed") from error


def _generate_gemini_text(
    user_text: str,
    history: list[dict[str, str]],
) -> str:
    from google import genai

    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)
    context = format_history(history)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=(
            f"{SYSTEM_PROMPT}\n\n"
            f"История диалога:\n{context}\n\n"
            f"Текущий вопрос пользователя:\n{user_text}"
        ),
    )

    text = getattr(response, "text", None)
    if not text:
        raise AIServiceError("Gemini returned an empty response")

    return text.strip()


def format_history(history: list[dict[str, str]]) -> str:
    if not history:
        return "Истории пока нет."

    lines = []
    for item in history[-8:]:
        role = item.get("role", "user")
        content = item.get("content", "").strip()
        if not content:
            continue
        if len(content) > 700:
            content = f"{content[:700]}..."
        role_name = "Пользователь" if role == "user" else "AI"
        lines.append(f"{role_name}: {content}")

    return "\n".join(lines) if lines else "Истории пока нет."
