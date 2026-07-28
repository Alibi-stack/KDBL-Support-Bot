import asyncio
import logging

from config import get_settings

logger = logging.getLogger(__name__)


class AIServiceError(RuntimeError):
    """Raised when the AI service cannot return a valid response."""


SYSTEM_PROMPT = """
Ты дружелюбный AI-помощник KDBL Support для helpdesk и рабочих вопросов.

Отвечай естественно, коротко и по делу на русском языке. Если это полезно,
добавь короткую казахскую версию после русского ответа. Не начинай каждый ответ
с представления и не повторяй ограничения бота без необходимости.

Помогай с техникой, доступами, интернетом, почтой, принтерами, документами,
рабочими программами и корпоративными сервисами: Lotus, 1C/1С, Office, Word,
Excel, PDF, браузер, VPN, ЭЦП, порталы и внутренние системы. Если пользователь
пишет про программу, файл, документ, подпись, отправку, вход, ошибку или доступ,
считай это рабочей helpdesk-задачей.

Учитывай историю диалога. Фразы "не помогло", "еще варианты", "та же задача",
"а дальше", "перечисли" и короткие уточнения понимай как продолжение предыдущей
проблемы. Не подменяй проблему другой темой.

Если данных мало, не отказывай. Дай 2-4 наиболее вероятных шага и попроси
уточнить систему, текст ошибки или прислать скриншот. Если пользователь прислал
или описал скриншот, помоги разобрать его по описанию.

Только если вопрос явно не связан с работой, техникой, программами или сервисами,
мягко скажи, что лучше обратиться к профильному специалисту, и предложи помочь с
рабочими системами.

Если проблема требует прав администратора, физического ремонта, доступа к личным
данным или ты не уверен в решении, в конце ответа отдельной строкой напиши:
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
            return await _get_local_it_fallback(user_text, history or [])

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


async def _get_local_it_fallback(
    user_text: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    lowered = user_text.lower()
    history_text = " ".join(
        item.get("content", "") for item in (history or [])[-6:]
    ).lower()
    combined = f"{history_text} {lowered}"

    if any(
        word in combined
        for word in ("комп", "компьютер", "завис", "зависает", "не отвечает")
    ):
        return (
            "Вот что можно попробовать:\n\n"
            "1. Подождите 1-2 минуты: возможно, система завершает обновление или "
            "тяжелую задачу.\n"
            "2. Нажмите Ctrl + Alt + Delete и попробуйте открыть Диспетчер задач.\n"
            "3. Если не помогает, удерживайте кнопку питания 5-10 секунд, затем "
            "включите компьютер снова.\n"
            "4. Если проблема повторяется, создайте тикет оператору.\n\n"
            "KDBL Support кеңесі: 1-2 минут күтіңіз, Ctrl + Alt + Delete басып "
            "көріңіз, көмектеспесе компьютерді қайта қосыңыз."
        )

    if any(word in combined for word in ("принтер", "печать", "басып")):
        return (
            "Вот что можно проверить:\n\n"
            "Проверьте питание принтера, бумагу, кабель/Wi-Fi, очередь печати и "
            "перезапустите принтер. Если не поможет, создайте тикет оператору."
        )

    if any(word in combined for word in ("word", "ворд", "doc", "docx")):
        return (
            "Попробуйте так:\n\n"
            "1. Закройте Word и откройте документ заново.\n"
            "2. Скопируйте файл на рабочий стол и попробуйте открыть копию.\n"
            "3. Проверьте, не открыт ли документ у другого пользователя.\n"
            "4. Откройте Word без файла и выберите: Файл -> Открыть -> "
            "Восстановить текст/Открыть и восстановить.\n"
            "5. Если появляется ошибка, отправьте ее текст или скриншот.\n\n"
            "Егер Word құжаты ашылмаса, файлдың көшірмесін жасап көріңіз, Word-ты "
            "қайта ашыңыз және қате мәтінін жіберіңіз."
        )

    if any(word in combined for word in ("pdf", "пдф")):
        return (
            "Попробуйте так:\n\n"
            "1. Скачайте PDF на компьютер и откройте локальную копию.\n"
            "2. Попробуйте открыть через другой просмотрщик или браузер.\n"
            "3. Проверьте, не поврежден ли файл: попросите отправить его повторно.\n"
            "4. Если PDF требует доступ или пароль, уточните у владельца файла.\n"
            "5. Если есть ошибка, отправьте ее текст или скриншот.\n\n"
            "PDF ашылмаса, файлды қайта жүктеп, басқа бағдарламада немесе браузерде "
            "ашып көріңіз. Қате болса, мәтінін жіберіңіз."
        )

    if any(
        word in combined
        for word in (
            "lotus",
            "1c",
            "1с",
            "office",
            "excel",
            "word",
            "ворд",
            "pdf",
            "пдф",
            "документ",
            "файл",
            "эцп",
            "vpn",
        )
    ):
        if any(word in lowered for word in ("найти", "поиск", "документ", "құжат")):
            return (
                "Чтобы найти документ в Lotus, обычно нужно:\n\n"
                "1. Открыть Lotus и войти под своей учетной записью.\n"
                "2. Перейти в нужную базу/раздел документов.\n"
                "3. Использовать поиск по названию, номеру, автору или дате.\n"
                "4. Если документ не находится, проверить фильтры и права доступа.\n\n"
                "Если напишете, какой именно документ ищете и где он должен быть, "
                "подскажу точнее.\n\n"
                "Lotus-та құжат табу үшін бөлімге кіріп, атауы/нөмірі/күні бойынша "
                "іздеп көріңіз. Табылмаса, фильтрлер мен қолжетімділікті тексеріңіз."
            )

        return (
            "Готов помочь. Уточните, пожалуйста, что именно нужно сделать: войти, "
            "найти документ, подписать, отправить, настроить доступ или исправить "
            "ошибку. Если есть текст ошибки или скриншот, отправьте его.\n\n"
            "Көмектесуге дайынмын. Нақты қандай әрекет керек екенін жазыңыз: "
            "кіру, құжат табу, қол қою, жіберу, қолжетімділік немесе қате."
        )

    return (
        "Уточните, пожалуйста, с какой рабочей системой или устройством нужна "
        "помощь и что именно не получается. Например: Lotus, 1С, почта, доступ, "
        "Word/PDF документ, принтер, интернет или компьютер.\n\n"
        "Қай жұмыс жүйесімен немесе құрылғымен көмек керек екенін нақтылап "
        "жазыңыз: Lotus, 1С, пошта, қолжетімділік, Word/PDF құжат, принтер, "
        "интернет немесе компьютер."
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
