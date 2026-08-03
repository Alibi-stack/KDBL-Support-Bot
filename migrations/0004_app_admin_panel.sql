CREATE TABLE IF NOT EXISTS app_users (
  telegram_user_id TEXT PRIMARY KEY,
  telegram_username TEXT,
  first_name TEXT,
  last_name TEXT,
  profile_department TEXT,
  support_department TEXT NOT NULL DEFAULT 'operator',
  access_level TEXT NOT NULL DEFAULT 'user',
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

ALTER TABLE app_tickets ADD COLUMN closed_at TEXT;
ALTER TABLE app_tickets ADD COLUMN closed_by_operator_name TEXT;

CREATE INDEX IF NOT EXISTS idx_app_tickets_department_status
  ON app_tickets(department, status);

CREATE INDEX IF NOT EXISTS idx_app_tickets_user_status
  ON app_tickets(telegram_user_id, status);

CREATE INDEX IF NOT EXISTS idx_app_users_department_level
  ON app_users(support_department, access_level);
