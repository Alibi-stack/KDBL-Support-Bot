"""
services/metrics.py -- Prometheus-метрики бота.

Метрики регистрируются здесь и отдаются по HTTP на /metrics (см.
start_metrics_server(), вызывается один раз из main.py при старте).
prometheus_client дополнительно публикует стандартные process-метрики
(CPU, память, GC) сам по себе, без дополнительного кода.

kdbl_tickets_total и kdbl_active_tickets инкрементируются прямо в
services/ticket_storage.py (create_ticket/close_ticket) -- этот файл уже
переписывается в рамках миграции на Postgres, поэтому это естественное
место для подключения счётчиков тикетов.

kdbl_messages_total, kdbl_ai_response_seconds и kdbl_ai_errors_total
объявлены и готовы к использованию, но не подключены к handlers/*.py и
services/ai_client.py в этой миграции (эти файлы сознательно не
трогаются, см. план). Подключить их -- дело одной строки в нужном месте
в следующей итерации.
"""

import logging

from prometheus_client import Counter, Gauge, Histogram, start_http_server

logger = logging.getLogger(__name__)

messages_total = Counter(
    "kdbl_messages_total",
    "Количество входящих сообщений от пользователей",
    ["type"],  # ai | ticket | command
)

ai_response_seconds = Histogram(
    "kdbl_ai_response_seconds",
    "Время генерации ответа AI (RAG + Grok), секунды",
)

ai_errors_total = Counter(
    "kdbl_ai_errors_total",
    "Количество ошибок AI/RAG-пайплайна",
)

tickets_total = Counter(
    "kdbl_tickets_total",
    "Количество обращений по статусу",
    ["status"],  # open | closed
)

active_tickets = Gauge(
    "kdbl_active_tickets",
    "Текущее количество открытых обращений (open + in_progress)",
)


def start_metrics_server(port: int = 8080) -> None:
    """Запускает HTTP-эндпоинт /metrics в фоновом треде prometheus_client."""
    try:
        start_http_server(port)
        logger.info("Prometheus metrics server started on :%s/metrics", port)
    except OSError:
        logger.exception("Cannot start Prometheus metrics server on port %s", port)
