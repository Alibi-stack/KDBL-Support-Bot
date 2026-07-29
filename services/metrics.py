"""
services/metrics.py -- Prometheus-метрики бота.

Метрики регистрируются здесь и отдаются по HTTP на /metrics (см.
start_metrics_server(), вызывается один раз из main.py при старте).
prometheus_client дополнительно публикует стандартные process-метрики
(CPU, память, GC) сам по себе, без дополнительного кода.

kdbl_tickets_total и kdbl_active_tickets инкрементируются в
services/ticket_storage.py (create_ticket/close_ticket).

kdbl_messages_total инкрементируется в handlers/*.py в точках входа
сообщений (ai/ticket/command). kdbl_ai_response_seconds и
kdbl_ai_errors_total инкрементируются в services/ai_client.py вокруг
вызова провайдера AI. kdbl_telegram_rate_limited_total инкрементируется
в main.py через глобальный error handler на TelegramRetryAfter (HTTP 429
от Telegram Bot API).
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

telegram_rate_limited_total = Counter(
    "kdbl_telegram_rate_limited_total",
    "Количество ошибок 429 (Too Many Requests) от Telegram Bot API",
)


def start_metrics_server(port: int = 8080) -> None:
    """Запускает HTTP-эндпоинт /metrics в фоновом треде prometheus_client."""
    try:
        start_http_server(port)
        logger.info("Prometheus metrics server started on :%s/metrics", port)
    except OSError:
        logger.exception("Cannot start Prometheus metrics server on port %s", port)
