"""
rag_engine.py — AI-модуль поддержки (зона CS: AI/LLM + RAG).
Версия под Gemini API (google-genai SDK).

Что делает:
1. Загружает базу знаний (knowledge_base.json).
2. Строит векторный индекс (ChromaDB + локальные multilingual-эмбеддинги,
   без внешнего API — дешевле и работает офлайн).
3. По вопросу пользователя находит top-k релевантных фрагментов FAQ.
4. Собирает system prompt (см. 1_system_prompts.md), зовёт Gemini API.
5. Возвращает результат в формате, согласованном с SE (см. JSON-контракт
   в 4_fsm_design.md) — этот словарь SE-часть бота просто передаёт дальше
   в Telegram-сообщение и кнопки.

Зависимости:
    pip install google-genai chromadb sentence-transformers python-dotenv

Переменные окружения (.env, формат согласован с Cybersecurity):
    GEMINI_API_KEY=...
    GEMINI_MODEL=gemini-3.5-flash     # 2.5-flash уже недоступна для новых ключей, см. ниже
    KB_PATH=./knowledge_base.json
    CHROMA_DIR=./chroma_store

Актуальный список моделей Gemini лучше сверять здесь перед запуском:
https://ai.google.dev/gemini-api/docs/models — линейка обновляется чаще,
чем хотелось бы: например, gemini-2.5-flash перестала выдаваться новым
ключам раньше официальной даты отключения (октябрь 2026). Если и
gemini-3.5-flash перестанет работать — попробуй gemini-3.1-flash-lite
(дешевле) или проверь актуальный список в Google AI Studio.
"""

import os
import json
import time
import logging
from typing import Any

from dotenv import load_dotenv
import chromadb
from sentence_transformers import SentenceTransformer
from google import genai
from google.genai import types

load_dotenv()

logger = logging.getLogger("rag_engine")
logging.basicConfig(level=logging.INFO)

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
KB_PATH = os.getenv("KB_PATH", "knowledge_base.json")
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_store")
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"  # хорошо работает с рус. языком

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)

PROMPT_PATH = os.getenv("PROMPT_PATH", os.path.join(os.path.dirname(__file__), "system_prompt.md"))
with open(PROMPT_PATH, "r", encoding="utf-8") as f:
    SYSTEM_PROMPT_TEMPLATE = f.read()


def load_knowledge_base(path: str = KB_PATH) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["items"]


def build_vector_store(kb: list[dict]):
    """Создаёт (или переиспользует) коллекцию в ChromaDB."""
    collection = chroma_client.get_or_create_collection(name="faq")
    if collection.count() > 0:
        logger.info("Коллекция уже проиндексирована (%s записей).", collection.count())
        return collection

    docs, ids, metadatas = [], [], []
    for item in kb:
        # объединяем вопрос + ключевые слова + ответ — так эмбеддинг ловит
        # и формулировку вопроса, и суть ответа
        text = f"{item['question']}. {' '.join(item['keywords'])}. {item['answer']}"
        docs.append(text)
        ids.append(item["id"])
        metadatas.append({"category": item["category"], "question": item["question"]})

    embeddings = embedder.encode(docs).tolist()
    collection.add(documents=docs, embeddings=embeddings, ids=ids, metadatas=metadatas)
    logger.info("Проиндексировано %s записей FAQ.", len(docs))
    return collection


def retrieve(query: str, collection, kb_by_id: dict, top_k: int = 3) -> list[dict]:
    """Возвращает top_k релевантных FAQ-статей целиком (с полным answer)."""
    query_embedding = embedder.encode([query]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=top_k)
    found_ids = results["ids"][0]
    return [kb_by_id[i] for i in found_ids if i in kb_by_id]


def format_context(faq_items: list[dict]) -> str:
    if not faq_items:
        return "(ничего релевантного не найдено в базе знаний)"
    blocks = []
    for item in faq_items:
        blocks.append(f"[{item['id']}] {item['question']}\nОтвет: {item['answer']}")
    return "\n\n".join(blocks)


def format_history(history: list[dict], max_turns: int = 6) -> str:
    if not history:
        return "(диалог только начался)"
    trimmed = history[-max_turns:]
    return "\n".join(f"{turn['role']}: {turn['content']}" for turn in trimmed)


def call_llm(system_prompt: str) -> dict[str, Any]:
    """Вызывает Gemini API и парсит строгий JSON-ответ модели.

    system_prompt уже содержит и инструкции, и подставленные RAG_CONTEXT /
    CHAT_HISTORY / USER_QUERY (см. answer_question ниже) — поэтому его
    целиком передаём как system_instruction, а в contents кладём короткую
    команду "ответь по формату".
    """
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents="Сформируй ответ строго в формате JSON, как указано в инструкции выше.",
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.3,
            max_output_tokens=800,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    raw_text = (response.text or "").strip()
    raw_text = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("Модель вернула невалидный JSON, включаю fallback-эскалацию.")
        logger.warning("Сырой ответ модели (для отладки): %r", raw_text)
        finish_reason = response.candidates[0].finish_reason if response.candidates else None
        logger.warning("finish_reason: %s", finish_reason)
        parsed = {
            "answer": "Не получилось обработать ваш вопрос автоматически. Подключаю оператора.",
            "confidence": "low",
            "escalate": True,
            "matched_faq_ids": [],
        }
    return parsed


# --- дешёвые проверки без вызова LLM (экономят запросы к API) -------------

ESCALATION_TRIGGERS = ["оператор", "человек", "не помогло", "живой сотрудник", "поговорить с человеком"]


def wants_operator(query: str) -> bool:
    q = query.lower()
    return any(trigger in q for trigger in ESCALATION_TRIGGERS)


# --- основная точка входа для SE-части -------------------------------------

def answer_question(user_query: str, history: list[dict] | None = None) -> dict[str, Any]:
    """
    Главная функция, которую вызывает Telegram-бот (зона SE).

    Вход:  user_query (str), history (список {"role": "user"/"assistant", "content": str})
    Выход: dict строго по контракту, см. 4_fsm_design.md:
        {
          "answer": str,
          "confidence": "high" | "medium" | "low",
          "escalate": bool,
          "matched_faq_ids": list[str],
          "latency_ms": int
        }
    """
    start = time.time()
    history = history or []

    if wants_operator(user_query):
        return {
            "answer": "Хорошо, подключаю оператора — он свяжется с вами в ближайшее время.",
            "confidence": "high",
            "escalate": True,
            "matched_faq_ids": [],
            "latency_ms": int((time.time() - start) * 1000),
        }

    kb = load_knowledge_base()
    kb_by_id = {item["id"]: item for item in kb}
    collection = build_vector_store(kb)

    relevant = retrieve(user_query, collection, kb_by_id, top_k=3)
    context = format_context(relevant)
    history_text = format_history(history)

    system_prompt = (
        SYSTEM_PROMPT_TEMPLATE
        .replace("{{RAG_CONTEXT}}", context)
        .replace("{{CHAT_HISTORY}}", history_text)
        .replace("{{USER_QUERY}}", user_query)
    )

    result = call_llm(system_prompt)
    result["latency_ms"] = int((time.time() - start) * 1000)
    return result


if __name__ == "__main__":
    test_query = "как поменять менеджера?"
    print(json.dumps(answer_question(test_query), ensure_ascii=False, indent=2))