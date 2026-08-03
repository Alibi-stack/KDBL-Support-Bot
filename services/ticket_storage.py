from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg

from config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Ticket:
    id: int
    user_id: int
    user_name: str
    username: str | None
    question: str
    status: str
    operator_id: int | None
    operator_name: str | None
    admin_chat_id: int | None
    admin_message_id: int | None
    admin_thread_id: int | None
    department: str
    routing_status: str
    routing_confidence: int | None
    routing_reason: str | None
    clarification_question: str | None
    clarification_count: int
    initial_department: str | None
    final_department: str | None
    routed_at: str | None


@dataclass(frozen=True)
class TicketReportRow:
    id: int
    user_id: int
    user_name: str
    username: str | None
    question: str
    status: str
    operator_name: str | None
    created_at: str
    updated_at: str
    closed_at: str | None


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    user_name TEXT NOT NULL,
    username TEXT,
    question TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    operator_id BIGINT,
    operator_name TEXT,
    admin_chat_id BIGINT,
    admin_message_id BIGINT,
    admin_thread_id BIGINT,
    department TEXT NOT NULL DEFAULT 'unknown',
    routing_status TEXT NOT NULL DEFAULT 'needs_review',
    routing_confidence INTEGER,
    routing_reason TEXT,
    clarification_question TEXT,
    clarification_count INTEGER NOT NULL DEFAULT 0,
    initial_department TEXT,
    final_department TEXT,
    routed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tickets_user_status
    ON tickets(user_id, status);

CREATE TABLE IF NOT EXISTS ticket_messages (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    sender_role TEXT NOT NULL,
    sender_id BIGINT NOT NULL,
    sender_name TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ticket_routing_history (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    event_type TEXT NOT NULL,
    from_department TEXT,
    to_department TEXT NOT NULL,
    routing_status TEXT NOT NULL,
    confidence INTEGER,
    reason TEXT,
    clarification_question TEXT,
    actor_id BIGINT,
    actor_name TEXT,
    llm_model TEXT,
    duration_ms INTEGER,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_type TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ticket_routing_history_ticket_id
    ON ticket_routing_history(ticket_id, id);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id BIGINT PRIMARY KEY,
    language TEXT NOT NULL DEFAULT 'ru',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS moderation_state (
    user_id BIGINT PRIMARY KEY,
    warnings INTEGER NOT NULL DEFAULT 0,
    muted_until TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_pool: asyncpg.Pool | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=get_settings().database_url,
            min_size=1,
            max_size=10,
        )
    return _pool


def _row_to_ticket(row: asyncpg.Record | None) -> Ticket | None:
    if row is None:
        return None
    return Ticket(
        id=row["id"],
        user_id=row["user_id"],
        user_name=row["user_name"],
        username=row["username"],
        question=row["question"],
        status=row["status"],
        operator_id=row["operator_id"],
        operator_name=row["operator_name"],
        admin_chat_id=row["admin_chat_id"],
        admin_message_id=row["admin_message_id"],
        admin_thread_id=row["admin_thread_id"],
        department=row["department"],
        routing_status=row["routing_status"],
        routing_confidence=row["routing_confidence"],
        routing_reason=row["routing_reason"],
        clarification_question=row["clarification_question"],
        clarification_count=row["clarification_count"],
        initial_department=row["initial_department"],
        final_department=row["final_department"],
        routed_at=row["routed_at"],
    )


async def init_db() -> None:
    pool = await _get_pool()
    async with pool.acquire() as connection:
        await connection.execute(SCHEMA_SQL)


async def create_ticket(
    user_id: int,
    user_name: str,
    username: str | None,
    question: str,
    admin_chat_id: int,
    department: str = "unknown",
    routing_status: str = "needs_review",
    routing_confidence: int | None = None,
    routing_reason: str | None = None,
    clarification_question: str | None = None,
    clarification_count: int = 0,
    initial_department: str | None = None,
    final_department: str | None = None,
    llm_model: str | None = None,
    routing_duration_ms: int | None = None,
    routing_success: bool = True,
    routing_error_type: str | None = None,
) -> Ticket:
    now = _now()
    pool = await _get_pool()
    async with pool.acquire() as connection, connection.transaction():
        ticket_id = await connection.fetchval(
            """
            INSERT INTO tickets (
                user_id, user_name, username, question, status,
                admin_chat_id, department, routing_status, routing_confidence,
                routing_reason, clarification_question, clarification_count,
                initial_department, final_department, routed_at, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, 'open', $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $14, $14)
            RETURNING id
            """,
            user_id,
            user_name,
            username,
            question,
            admin_chat_id,
            department,
            routing_status,
            routing_confidence,
            routing_reason,
            clarification_question,
            clarification_count,
            initial_department or department,
            final_department or department,
            now,
        )
        await connection.execute(
            """
            INSERT INTO ticket_messages (
                ticket_id, sender_role, sender_id, sender_name, text, created_at
            )
            VALUES ($1, 'user', $2, $3, $4, $5)
            """,
            ticket_id,
            user_id,
            user_name,
            question,
            now,
        )
        await connection.execute(
            """
            INSERT INTO ticket_routing_history (
                ticket_id, event_type, from_department, to_department,
                routing_status, confidence, reason, clarification_question,
                llm_model, duration_ms, success, error_type, created_at
            )
            VALUES ($1, 'auto_classified', NULL, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            ticket_id,
            department,
            routing_status,
            routing_confidence,
            routing_reason,
            clarification_question,
            llm_model,
            routing_duration_ms,
            routing_success,
            routing_error_type,
            now,
        )
        row = await connection.fetchrow(
            "SELECT * FROM tickets WHERE id = $1",
            ticket_id,
        )
    ticket = _row_to_ticket(row)
    assert ticket is not None

    from services import metrics

    metrics.tickets_total.labels(status="open").inc()
    metrics.active_tickets.inc()

    return ticket


async def get_ticket(ticket_id: int) -> Ticket | None:
    pool = await _get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            "SELECT * FROM tickets WHERE id = $1",
            ticket_id,
        )
    return _row_to_ticket(row)


async def get_active_ticket_by_user(user_id: int) -> Ticket | None:
    pool = await _get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT * FROM tickets
            WHERE user_id = $1 AND status IN ('open', 'in_progress')
            ORDER BY id DESC
            LIMIT 1
            """,
            user_id,
        )
    return _row_to_ticket(row)


async def get_active_ticket_by_operator(operator_id: int) -> Ticket | None:
    pool = await _get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT * FROM tickets
            WHERE operator_id = $1 AND status = 'in_progress'
            ORDER BY id DESC
            LIMIT 1
            """,
            operator_id,
        )
    return _row_to_ticket(row)


async def get_ticket_by_thread(
    admin_chat_id: int,
    admin_thread_id: int,
) -> Ticket | None:
    pool = await _get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT * FROM tickets
            WHERE admin_chat_id = $1 AND admin_thread_id = $2
            ORDER BY id DESC
            LIMIT 1
            """,
            admin_chat_id,
            admin_thread_id,
        )
    return _row_to_ticket(row)


async def _update_ticket(ticket_id: int, **fields: Any) -> Ticket | None:
    if not fields:
        return await get_ticket(ticket_id)

    fields["updated_at"] = _now()
    names = list(fields.keys())
    values = list(fields.values())
    assignments = ", ".join(f"{name} = ${i + 1}" for i, name in enumerate(names))

    pool = await _get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            f"UPDATE tickets SET {assignments} WHERE id = ${len(values) + 1}",
            *values,
            ticket_id,
        )
        row = await connection.fetchrow(
            "SELECT * FROM tickets WHERE id = $1",
            ticket_id,
        )
    return _row_to_ticket(row)


async def set_ticket_admin_message(ticket_id: int, message_id: int) -> Ticket | None:
    return await _update_ticket(ticket_id, admin_message_id=message_id)


async def set_ticket_admin_thread(ticket_id: int, thread_id: int) -> Ticket | None:
    return await _update_ticket(ticket_id, admin_thread_id=thread_id)


async def assign_ticket(
    ticket_id: int,
    operator_id: int,
    operator_name: str,
) -> Ticket | None:
    return await _update_ticket(
        ticket_id,
        status="in_progress",
        operator_id=operator_id,
        operator_name=operator_name,
    )


async def release_ticket(ticket_id: int) -> Ticket | None:
    return await _update_ticket(
        ticket_id,
        status="open",
        operator_id=None,
        operator_name=None,
    )


async def reassign_ticket_route(
    ticket_id: int,
    department: str,
    actor_id: int | None,
    actor_name: str | None,
    admin_chat_id: int | None = None,
    admin_thread_id: int | None = None,
    reason: str = "Manual reassignment by operator.",
) -> Ticket | None:
    now = _now()
    pool = await _get_pool()
    async with pool.acquire() as connection, connection.transaction():
        old_department = await connection.fetchval(
            "SELECT department FROM tickets WHERE id = $1",
            ticket_id,
        )
        await connection.execute(
            """
            UPDATE tickets
            SET department = $1,
                final_department = $1,
                routing_status = 'manually_reassigned',
                routing_reason = $2,
                admin_chat_id = COALESCE($3, admin_chat_id),
                admin_thread_id = $4,
                updated_at = $5
            WHERE id = $6
            """,
            department,
            reason,
            admin_chat_id,
            admin_thread_id,
            now,
            ticket_id,
        )
        await connection.execute(
            """
            INSERT INTO ticket_routing_history (
                ticket_id, event_type, from_department, to_department,
                routing_status, confidence, reason, actor_id, actor_name,
                created_at
            )
            VALUES ($1, 'manual_reassigned', $2, $3, 'manually_reassigned', NULL, $4, $5, $6, $7)
            """,
            ticket_id,
            old_department,
            department,
            reason,
            actor_id,
            actor_name,
            now,
        )
        row = await connection.fetchrow("SELECT * FROM tickets WHERE id = $1", ticket_id)
    return _row_to_ticket(row)


async def close_ticket(ticket_id: int) -> Ticket | None:
    ticket = await _update_ticket(
        ticket_id,
        status="closed",
        closed_at=_now(),
    )

    if ticket is not None:
        from services import metrics

        metrics.tickets_total.labels(status="closed").inc()
        metrics.active_tickets.dec()

    return ticket


async def add_message(
    ticket_id: int,
    sender_role: str,
    sender_id: int,
    sender_name: str,
    text: str,
) -> None:
    now = _now()
    pool = await _get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO ticket_messages (
                ticket_id, sender_role, sender_id, sender_name, text, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            ticket_id,
            sender_role,
            sender_id,
            sender_name,
            text,
            now,
        )
        await connection.execute(
            "UPDATE tickets SET updated_at = $1 WHERE id = $2",
            now,
            ticket_id,
        )


async def get_user_language(user_id: int) -> str | None:
    pool = await _get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            "SELECT language FROM user_settings WHERE user_id = $1",
            user_id,
        )
    return row["language"] if row else None


async def set_user_language(user_id: int, language: str) -> None:
    now = _now()
    pool = await _get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO user_settings (user_id, language, created_at, updated_at)
            VALUES ($1, $2, $3, $3)
            ON CONFLICT (user_id) DO UPDATE SET
                language = EXCLUDED.language,
                updated_at = EXCLUDED.updated_at
            """,
            user_id,
            language,
            now,
        )


async def get_moderation_state(user_id: int) -> tuple[int, str | None]:
    pool = await _get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            "SELECT warnings, muted_until FROM moderation_state WHERE user_id = $1",
            user_id,
        )
    if row is None:
        return 0, None
    return row["warnings"], row["muted_until"]


async def set_moderation_state(
    user_id: int,
    warnings: int,
    muted_until: str | None,
) -> None:
    now = _now()
    pool = await _get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO moderation_state (user_id, warnings, muted_until, updated_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE SET
                warnings = EXCLUDED.warnings,
                muted_until = EXCLUDED.muted_until,
                updated_at = EXCLUDED.updated_at
            """,
            user_id,
            warnings,
            muted_until,
            now,
        )


async def get_app_state(key: str) -> str | None:
    pool = await _get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            "SELECT value FROM app_state WHERE key = $1",
            key,
        )
    return row["value"] if row else None


async def set_app_state(key: str, value: str) -> None:
    pool = await _get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO app_state (key, value, updated_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = EXCLUDED.updated_at
            """,
            key,
            value,
            _now(),
        )


async def set_app_state_if_changed(key: str, value: str) -> bool:
    pool = await _get_pool()
    async with pool.acquire() as connection:
        changed = await connection.fetchval(
            """
            INSERT INTO app_state (key, value, updated_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = EXCLUDED.updated_at
            WHERE app_state.value IS DISTINCT FROM EXCLUDED.value
            RETURNING 1
            """,
            key,
            value,
            _now(),
        )
    return changed == 1


async def get_tickets_for_period(
    start_iso: str,
    end_iso: str,
) -> list[TicketReportRow]:
    pool = await _get_pool()
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                id, user_id, user_name, username, question, status,
                operator_name, created_at, updated_at, closed_at
            FROM tickets
            WHERE created_at >= $1 AND created_at < $2
            ORDER BY id
            """,
            start_iso,
            end_iso,
        )
    return [
        TicketReportRow(
            id=row["id"],
            user_id=row["user_id"],
            user_name=row["user_name"],
            username=row["username"],
            question=row["question"],
            status=row["status"],
            operator_name=row["operator_name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
        )
        for row in rows
    ]
