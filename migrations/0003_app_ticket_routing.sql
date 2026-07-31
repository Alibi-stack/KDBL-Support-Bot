ALTER TABLE app_tickets ADD COLUMN routing_status TEXT NOT NULL DEFAULT 'needs_review';
ALTER TABLE app_tickets ADD COLUMN routing_confidence INTEGER;
ALTER TABLE app_tickets ADD COLUMN routing_reason TEXT;
ALTER TABLE app_tickets ADD COLUMN clarification_question TEXT;
ALTER TABLE app_tickets ADD COLUMN clarification_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE app_tickets ADD COLUMN initial_department TEXT;
ALTER TABLE app_tickets ADD COLUMN final_department TEXT;
ALTER TABLE app_tickets ADD COLUMN routed_at TEXT;

CREATE TABLE IF NOT EXISTS app_ticket_routing_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  from_department TEXT,
  to_department TEXT NOT NULL,
  routing_status TEXT NOT NULL,
  confidence INTEGER,
  reason TEXT,
  clarification_question TEXT,
  actor_id TEXT,
  actor_name TEXT,
  llm_model TEXT,
  duration_ms INTEGER,
  success INTEGER NOT NULL DEFAULT 1,
  error_type TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (ticket_id) REFERENCES app_tickets(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_app_ticket_routing_history_ticket_id
  ON app_ticket_routing_history(ticket_id, id);
