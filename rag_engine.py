"""
rag_engine.py — поиск по базе знаний (RAG retrieval).

Что делает:
1. Загружает базу знаний (knowledge_base.json).
2. Строит векторный индекс (ChromaDB + локальные multilingual-эмбеддинги,
   без внешнего API — дешевле и работает офлайн).
3. По вопросу пользователя находит top-k релевантных фрагментов FAQ.

Генерация самого ответа (вызов LLM) находится в services/ai_client.py —
там собирается system prompt и в него подставляется контекст, который
возвращает этот модуль (см. SYSTEM_PROMPT и {{RAG_CONTEXT}} в ai_client.py).

Зависимости:
    pip install chromadb sentence-transformers

Переменные окружения (.env, читаются через config.get_settings()):
    KB_PATH=knowledge_base.json
    CHROMA_DIR=./chroma_store
"""

import json
import logging
from functools import lru_cache

from config import get_settings

logger = logging.getLogger("rag_engine")

EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"  # хорошо работает с рус. языком
COLLECTION_NAME = "faq"

ESCALATION_TRIGGERS = ["оператор", "человек", "не помогло", "живой сотрудник", "поговорить с человеком"]


def load_knowledge_base(path: str | None = None) -> list[dict]:
    kb_path = path or get_settings().kb_path
    with open(kb_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["items"]


@lru_cache(maxsize=1)
def _get_embedder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL_NAME)


@lru_cache(maxsize=1)
def _get_collection():
    """Строит (или переиспользует) коллекцию в ChromaDB и кэширует её в памяти
    процесса, чтобы не переиндексировать базу знаний на каждый вопрос."""
    import chromadb

    kb = load_knowledge_base()
    embedder = _get_embedder()
    chroma_client = chromadb.PersistentClient(path=get_settings().chroma_dir)
    collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)

    if collection.count() == 0:
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
    else:
        logger.info("Коллекция уже проиндексирована (%s записей).", collection.count())

    kb_by_id = {item["id"]: item for item in kb}
    return collection, kb_by_id


def retrieve_relevant_faq(query: str, top_k: int = 3) -> list[dict]:
    """Возвращает top_k релевантных FAQ-статей целиком (с полным answer)."""
    collection, kb_by_id = _get_collection()
    query_embedding = _get_embedder().encode([query]).tolist()
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


# --- дешёвая проверка без вызова LLM (экономит запросы к API) --------------


def wants_operator(query: str) -> bool:
    q = query.lower()
    return any(trigger in q for trigger in ESCALATION_TRIGGERS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_query = "как поменять менеджера?"
    print(json.dumps(retrieve_relevant_faq(test_query), ensure_ascii=False, indent=2))
