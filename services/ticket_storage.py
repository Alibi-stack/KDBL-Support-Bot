from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import get_settings


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


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    db_path = Path(get_settings().database_path)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def _row_to_ticket(row: sqlite3.Row | None) -> Ticket | None:
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
    )


def _init_db_sync() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                username TEXT,
                question TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                operator_id INTEGER,
                operator_name TEXT,
                admin_chat_id INTEGER,
                admin_message_id INTEGER,
                admin_thread_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                closed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_tickets_user_status
                ON tickets(user_id, status);

            CREATE TABLE IF NOT EXISTS ticket_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                sender_role TEXT NOT NULL,
                sender_id INTEGER NOT NULL,
                sender_name TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(ticket_id) REFERENCES tickets(id)
            );

            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                language TEXT NOT NULL DEFAULT 'ru',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS moderation_state (
                user_id INTEGER PRIMARY KEY,
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
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(tickets)").fetchall()
        }
        if "admin_thread_id" not in columns:
            connection.execute("ALTER TABLE tickets ADD COLUMN admin_thread_id INTEGER")


async def init_db() -> None:
    await asyncio.to_thread(_init_db_sync)


def _create_ticket_sync(
    user_id: int,
    user_name: str,
    username: str | None,
    question: str,
    admin_chat_id: int,
) -> Ticket:
    now = _now()
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO tickets (
                user_id, user_name, username, question, status,
                admin_chat_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (user_id, user_name, username, question, admin_chat_id, now, now),
        )
        ticket_id = cursor.lastrowid
        connection.execute(
            """
            INSERT INTO ticket_messages (
                ticket_id, sender_role, sender_id, sender_name, text, created_at
            )
            VALUES (?, 'user', ?, ?, ?, ?)
            """,
            (ticket_id, user_id, user_name, question, now),
        )
        row = connection.execute(
            "SELECT * FROM tickets WHERE id = ?",
            (ticket_id,),
        ).fetchone()
    ticket = _row_to_ticket(row)
    assert ticket is not None
    return ticket


async def create_ticket(
    user_id: int,
    user_name: str,
    username: str | None,
    question: str,
    admin_chat_id: int,
) -> Ticket:
    return await asyncio.to_thread(
        _create_ticket_sync,
        user_id,
        user_name,
        username,
        question,
        admin_chat_id,
    )


def _get_ticket_sync(ticket_id: int) -> Ticket | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM tickets WHERE id = ?",
            (ticket_id,),
        ).fetchone()
    return _row_to_ticket(row)


async def get_ticket(ticket_id: int) -> Ticket | None:
    return await asyncio.to_thread(_get_ticket_sync, ticket_id)


def _get_active_ticket_by_user_sync(user_id: int) -> Ticket | None:
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM tickets
            WHERE user_id = ? AND status IN ('open', 'in_progress')
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    return _row_to_ticket(row)


async def get_active_ticket_by_user(user_id: int) -> Ticket | None:
    return await asyncio.to_thread(_get_active_ticket_by_user_sync, user_id)


def _get_active_ticket_by_operator_sync(operator_id: int) -> Ticket | None:
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM tickets
            WHERE operator_id = ? AND status = 'in_progress'
            ORDER BY id DESC
            LIMIT 1
            """,
            (operator_id,),
        ).fetchone()
    return _row_to_ticket(row)


async def get_active_ticket_by_operator(operator_id: int) -> Ticket | None:
    return await asyncio.to_thread(_get_active_ticket_by_operator_sync, operator_id)


def _get_ticket_by_thread_sync(
    admin_chat_id: int,
    admin_thread_id: int,
) -> Ticket | None:
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM tickets
            WHERE admin_chat_id = ? AND admin_thread_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (admin_chat_id, admin_thread_id),
        ).fetchone()
    return _row_to_ticket(row)


async def get_ticket_by_thread(
    admin_chat_id: int,
    admin_thread_id: int,
) -> Ticket | None:
    return await asyncio.to_thread(
        _get_ticket_by_thread_sync,
        admin_chat_id,
        admin_thread_id,
    )


def _update_ticket_sync(ticket_id: int, **fields: Any) -> Ticket | None:
    if not fields:
        return _get_ticket_sync(ticket_id)

    fields["updated_at"] = _now()
    assignments = ", ".join(f"{name} = ?" for name in fields)
    values = list(fields.values())
    values.append(ticket_id)

    with _connect() as connection:
        connection.execute(
            f"UPDATE tickets SET {assignments} WHERE id = ?",
            values,
        )
        row = connection.execute(
            "SELECT * FROM tickets WHERE id = ?",
            (ticket_id,),
        ).fetchone()
    return _row_to_ticket(row)


async def set_ticket_admin_message(ticket_id: int, message_id: int) -> Ticket | None:
    return await asyncio.to_thread(
        _update_ticket_sync,
        ticket_id,
        admin_message_id=message_id,
    )


async def set_ticket_admin_thread(ticket_id: int, thread_id: int) -> Ticket | None:
    return await asyncio.to_thread(
        _update_ticket_sync,
        ticket_id,
        admin_thread_id=thread_id,
    )


async def assign_ticket(
    ticket_id: int,
    operator_id: int,
    operator_name: str,
) -> Ticket | None:
    return await asyncio.to_thread(
        _update_ticket_sync,
        ticket_id,
        status="in_progress",
        operator_id=operator_id,
        operator_name=operator_name,
    )


async def close_ticket(ticket_id: int) -> Ticket | None:
    return await asyncio.to_thread(
        _update_ticket_sync,
        ticket_id,
        status="closed",
        closed_at=_now(),
    )


def _add_message_sync(
    ticket_id: int,
    sender_role: str,
    sender_id: int,
    sender_name: str,
    text: str,
) -> None:
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO ticket_messages (
                ticket_id, sender_role, sender_id, sender_name, text, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ticket_id, sender_role, sender_id, sender_name, text, _now()),
        )
        connection.execute(
            "UPDATE tickets SET updated_at = ? WHERE id = ?",
            (_now(), ticket_id),
        )


async def add_message(
    ticket_id: int,
    sender_role: str,
    sender_id: int,
    sender_name: str,
    text: str,
) -> None:
    await asyncio.to_thread(
        _add_message_sync,
        ticket_id,
        sender_role,
        sender_id,
        sender_name,
        text,
    )


def _get_user_language_sync(user_id: int) -> str | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT language FROM user_settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row["language"] if row else None


async def get_user_language(user_id: int) -> str | None:
    return await asyncio.to_thread(_get_user_language_sync, user_id)


def _set_user_language_sync(user_id: int, language: str) -> None:
    now = _now()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO user_settings (user_id, language, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                language = excluded.language,
                updated_at = excluded.updated_at
            """,
            (user_id, language, now, now),
        )


async def set_user_language(user_id: int, language: str) -> None:
    await asyncio.to_thread(_set_user_language_sync, user_id, language)


def _get_moderation_state_sync(user_id: int) -> tuple[int, str | None]:
    with _connect() as connection:
        row = connection.execute(
            "SELECT warnings, muted_until FROM moderation_state WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return 0, None
    return row["warnings"], row["muted_until"]


async def get_moderation_state(user_id: int) -> tuple[int, str | None]:
    return await asyncio.to_thread(_get_moderation_state_sync, user_id)


def _set_moderation_state_sync(
    user_id: int,
    warnings: int,
    muted_until: str | None,
) -> None:
    now = _now()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO moderation_state (user_id, warnings, muted_until, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                warnings = excluded.warnings,
                muted_until = excluded.muted_until,
                updated_at = excluded.updated_at
            """,
            (user_id, warnings, muted_until, now),
        )


async def set_moderation_state(
    user_id: int,
    warnings: int,
    muted_until: str | None,
) -> None:
    await asyncio.to_thread(_set_moderation_state_sync, user_id, warnings, muted_until)


def _get_app_state_sync(key: str) -> str | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT value FROM app_state WHERE key = ?",
            (key,),
        ).fetchone()
    return row["value"] if row else None


async def get_app_state(key: str) -> str | None:
    return await asyncio.to_thread(_get_app_state_sync, key)


def _set_app_state_sync(key: str, value: str) -> None:
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO app_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, _now()),
        )


async def set_app_state(key: str, value: str) -> None:
    await asyncio.to_thread(_set_app_state_sync, key, value)


def _get_tickets_for_period_sync(
    start_iso: str,
    end_iso: str,
) -> list[TicketReportRow]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                id, user_id, user_name, username, question, status,
                operator_name, created_at, updated_at, closed_at
            FROM tickets
            WHERE created_at >= ? AND created_at < ?
            ORDER BY id
            """,
            (start_iso, end_iso),
        ).fetchall()
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


async def get_tickets_for_period(
    start_iso: str,
    end_iso: str,
) -> list[TicketReportRow]:
    return await asyncio.to_thread(_get_tickets_for_period_sync, start_iso, end_iso)
