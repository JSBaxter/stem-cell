PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tasks (
  id                TEXT PRIMARY KEY,
  title             TEXT NOT NULL,
  description       TEXT,
  status            TEXT NOT NULL DEFAULT 'idea',
  priority          INTEGER NOT NULL DEFAULT 50,
  parent_id         TEXT REFERENCES tasks(id),
  depends_on        TEXT NOT NULL DEFAULT '[]',
  relevant_files    TEXT NOT NULL DEFAULT '[]',
  relevant_services TEXT NOT NULL DEFAULT '[]',
  agent_hint        TEXT,
  notes             TEXT,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  id                 TEXT PRIMARY KEY,
  task_id            TEXT NOT NULL REFERENCES tasks(id),
  stage              TEXT NOT NULL,
  agent_id           TEXT NOT NULL,
  model_name         TEXT,
  model_family       TEXT,
  model_version      TEXT,
  operating_mode     TEXT,
  rule_set_version   TEXT,
  instructions_fingerprint TEXT,
  session_ref        TEXT,
  skills_used        TEXT NOT NULL DEFAULT '[]',
  tool_calls_summary TEXT NOT NULL DEFAULT '{}',
  tool_calls_summary_tokens_in INTEGER NOT NULL DEFAULT 0,
  tool_calls_summary_tokens_out INTEGER NOT NULL DEFAULT 0,
  tool_calls_summary_cache_read INTEGER NOT NULL DEFAULT 0,
  tool_calls_summary_cache_write INTEGER NOT NULL DEFAULT 0,
  design_patterns    TEXT NOT NULL DEFAULT '[]',
  decision_notes     TEXT,
  theory_notes       TEXT,
  tokens_in          INTEGER NOT NULL DEFAULT 0,
  tokens_out         INTEGER NOT NULL DEFAULT 0,
  tokens_cache_read  INTEGER NOT NULL DEFAULT 0,
  tokens_cache_write INTEGER NOT NULL DEFAULT 0,
  outcome            TEXT,
  summary            TEXT,
  notes              TEXT,
  artifacts          TEXT NOT NULL DEFAULT '[]',
  started_at         TEXT NOT NULL,
  ended_at           TEXT
);

CREATE TABLE IF NOT EXISTS task_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id     TEXT NOT NULL REFERENCES tasks(id),
  from_status TEXT,
  to_status   TEXT,
  actor       TEXT NOT NULL,
  note        TEXT,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feature_requests (
  id                  TEXT PRIMARY KEY,
  title               TEXT NOT NULL,
  kind                TEXT NOT NULL,
  detail              TEXT NOT NULL,
  status              TEXT NOT NULL DEFAULT 'open',
  task_id             TEXT REFERENCES tasks(id),
  session_id          TEXT REFERENCES sessions(id),
  agent_id            TEXT,
  model_name          TEXT,
  notes               TEXT,
  resolution          TEXT,
  resolution_task_id  TEXT REFERENCES tasks(id),
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status_priority
  ON tasks(status, priority, created_at);

CREATE INDEX IF NOT EXISTS idx_sessions_task_id
  ON sessions(task_id);

CREATE INDEX IF NOT EXISTS idx_task_events_task_id
  ON task_events(task_id, id);

CREATE INDEX IF NOT EXISTS idx_feature_requests_status
  ON feature_requests(status, created_at);
