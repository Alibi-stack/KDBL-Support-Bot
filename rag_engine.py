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
    CHROMA_HOST=localhost   # в Docker: chromadb (имя сервиса)
    CHROMA_PORT=8000        # ChromaDB Server (HttpClient)
"""

import json
import logging
import re
from functools import lru_cache

from config import get_settings

logger = logging.getLogger("rag_engine")

EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"  # хорошо работает с рус. языком
COLLECTION_NAME = "faq"

ESCALATION_TRIGGERS = ["оператор", "человек", "не помогло", "живой сотрудник", "поговорить с человеком"]
SEARCH_STOPWORDS = {
    "как",
    "что",
    "где",
    "при",
    "для",
    "или",
    "если",
    "это",
    "нет",
    "работает",
    "работать",
    "проблема",
    "проблемы",
    "ошибка",
    "нужно",
    "можно",
}


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
    settings = get_settings()
    chroma_client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
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
    lexical_matches = retrieve_relevant_faq_lexical(query, top_k=top_k)
    if lexical_matches or not get_settings().use_vector_rag:
        return lexical_matches

    try:
        collection, kb_by_id = _get_collection()
        query_embedding = _get_embedder().encode([query]).tolist()
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=top_k,
            include=["distances"],
        )
        found_ids = [
            item_id
            for item_id, distance in zip(results["ids"][0], results["distances"][0])
            if distance <= 0.9
        ]
        return [kb_by_id[i] for i in found_ids if i in kb_by_id]
    except Exception:
        logger.exception("Векторный RAG недоступен, использую простой поиск по базе знаний")
        return []


def retrieve_relevant_faq_lexical(query: str, top_k: int = 3) -> list[dict]:
    """Запасной поиск без ChromaDB и sentence-transformers.

    Он нужен для первого запуска или нестабильного интернета, когда локальная
    embedding-модель ещё не скачалась с HuggingFace.
    """
    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return []

    scored_items = []
    for item in load_knowledge_base():
        searchable = " ".join(
            [
                item.get("question", ""),
                " ".join(item.get("keywords", [])),
                item.get("category", ""),
            ]
        )
        item_tokens = set(_tokenize(searchable))
        score = len(query_tokens & item_tokens)
        for keyword in item.get("keywords", []):
            if keyword.lower() in query.lower():
                score += 3
        if score:
            scored_items.append((score, item))

    scored_items.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored_items[:top_k]]


def _tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-zа-яё0-9]+", text.lower())
        if len(token) > 2 and token not in SEARCH_STOPWORDS
    ]


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
