CREATE TABLE IF NOT EXISTS app_tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  telegram_user_id TEXT,
  telegram_username TEXT,
  user_name TEXT NOT NULL,
  first_name TEXT,
  last_name TEXT,
  department TEXT,
  category TEXT,
  priority TEXT,
  question TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  admin_chat_id TEXT,
  admin_message_id TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS app_ticket_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id INTEGER NOT NULL,
  sender_role TEXT NOT NULL,
  sender_name TEXT NOT NULL,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (ticket_id) REFERENCES app_tickets(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_app_ticket_messages_ticket_id
  ON app_ticket_messages(ticket_id, id);
