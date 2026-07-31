-- Схема БД для KDBL-Support-Bot (тикеты, сообщения, настройки, модерация).
--
-- Выполняется автоматически Postgres-контейнером при первом старте на
-- пустом volume (docker-entrypoint-initdb.d). Дублирует SCHEMA_SQL из
-- services/ticket_storage.py::init_db(), которая тоже идемпотентно создаёт
-- эти таблицы при каждом запуске бота -- на случай подключения к
-- Postgres, не поднятому этим docker-compose.

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
