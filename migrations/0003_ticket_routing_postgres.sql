ALTER TABLE tickets ADD COLUMN IF NOT EXISTS department TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS routing_status TEXT NOT NULL DEFAULT 'needs_review';
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS routing_confidence INTEGER;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS routing_reason TEXT;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS clarification_question TEXT;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS clarification_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS initial_department TEXT;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS final_department TEXT;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS routed_at TEXT;

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
