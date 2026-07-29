"""services/audit.py -- структурированный audit-лог действий по тикетам.

Обычные логи в проекте уже пишутся в JSON (main.py::configure_logging), а
python-json-logger раскладывает поля из logger.info(..., extra={...}) в
плоский JSON. Поэтому для audit-трейла ("кто, что и когда сделал") не
нужна отдельная таблица в БД -- достаточно писать такие записи через
отдельный логгер "audit" с предсказуемым набором полей.

Как искать в логах на VM:
    docker compose logs bot | grep '"logger": "audit"'
    docker compose logs bot | grep '"audit_action": "ticket_closed"'

Каждая запись содержит audit_action (ticket_created, ticket_assigned,
ticket_transferred, ticket_closed, operator_message, user_warned,
user_muted) и произвольные дополнительные поля (ticket_id, operator_id,
operator_name, user_id и т.д.) -- этого достаточно для расследования
инцидентов и как источник данных для отчётности.
"""

from __future__ import annotations

import logging

audit_logger = logging.getLogger("audit")


def log_event(action: str, **fields: object) -> None:
    """Пишет одну audit-запись с указанным действием и произвольными полями."""
    audit_logger.info(action, extra={"audit_action": action, **fields})
