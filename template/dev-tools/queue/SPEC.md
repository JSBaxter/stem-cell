# Cell Task Queue — Agent Handoff

Build a task queue as an MCP server.

Design bias: capture the operational data agents can practically provide
without turning every call into paperwork. If a field is available, store
it. If it is unavailable, omit it without error.

Development rule: implement in small coherent slices and commit after a
green checkpoint. Do not let the project drift for a long stretch as one
large uncommitted change.

## Architecture

Structure the project as three distinct layers:

- **Domain layer** (`domain/`) — pure Python, no I/O, no frameworks. Contains models, commands, events, and a `QueueService` that handles commands and returns events.
- **Infrastructure layer** (`infra/`) — SQLite repository implementing the domain's `QueueRepository` protocol.
- **Server layer** (`server.py`) — fastmcp MCP server. Thin dispatch only, no business logic.

`QueueService` must depend on a `QueueRepository` protocol, not a concrete class. Tests use an `InMemoryRepository`. The SQLite implementation is a drop-in replacement.

---

## Project Layout

```
queue/
├── domain/
│   ├── models.py        # Task, Session, TaskEvent — pure dataclasses
│   ├── commands.py      # one dataclass per command
│   ├── events.py        # one dataclass per domain event
│   └── queue.py         # QueueService — all business logic lives here
├── infra/
│   ├── repository.py    # SQLiteRepository implementing QueueRepository protocol
│   └── schema.sql
├── tests/
│   ├── fixtures.py      # InMemoryRepository + helpers
│   └── test_queue.py    # tests against QueueService only, no server or DB
├── server.py            # fastmcp — dispatches to QueueService, nothing else
└── README.md            # tool reference and example calls
```

---

## Schema

```sql
CREATE TABLE tasks (
  id                TEXT PRIMARY KEY,
  title             TEXT NOT NULL,
  description       TEXT,
  status            TEXT NOT NULL DEFAULT 'idea',
  priority          INTEGER DEFAULT 50,
  parent_id         TEXT REFERENCES tasks(id),
  depends_on        TEXT,         -- JSON array of task IDs
  relevant_files    TEXT,         -- JSON array
  relevant_services TEXT,         -- JSON array
  agent_hint        TEXT,
  notes             TEXT,
  created_at        TEXT DEFAULT (datetime('now')),
  updated_at        TEXT DEFAULT (datetime('now'))
);

CREATE TABLE sessions (
  id                 TEXT PRIMARY KEY,
  task_id            TEXT NOT NULL REFERENCES tasks(id),
  stage              TEXT NOT NULL,  -- 'scoping' | 'execution' | 'review'
  agent_id           TEXT,           -- harness identity, e.g. claude-code, codex
  model_name         TEXT,            -- canonical slug, e.g. claude-opus-4-7, gpt-5.5
  model_family       TEXT,            -- model line, e.g. claude-opus, gpt
  model_version      TEXT,            -- release within the family, e.g. 4-7, 5.5
  operating_mode     TEXT,           -- e.g. default, plan, review
  rule_set_version   TEXT,           -- human-readable rules/prompt bundle version
  instructions_fingerprint TEXT,     -- hash/fingerprint of the effective instructions
  session_ref        TEXT,           -- freeform: conversation URL, git SHA, tmux session, etc
  skills_used        TEXT,           -- JSON array of skills / named workflows
  tool_calls_summary TEXT,           -- JSON object of tool name/family -> count
  tool_calls_summary_tokens_in INTEGER DEFAULT 0,
  tool_calls_summary_tokens_out INTEGER DEFAULT 0,
  tool_calls_summary_cache_read INTEGER DEFAULT 0,
  tool_calls_summary_cache_write INTEGER DEFAULT 0,
  design_patterns    TEXT,           -- JSON array of patterns/architectures the agent thinks it is using
  decision_notes     TEXT,           -- why a path was chosen over alternatives
  theory_notes       TEXT,           -- optional mathematical/formal reasoning notes
  tokens_in          INTEGER DEFAULT 0,
  tokens_out         INTEGER DEFAULT 0,
  tokens_cache_read  INTEGER DEFAULT 0,
  tokens_cache_write INTEGER DEFAULT 0,
  outcome            TEXT,           -- 'completed' | 'failed' | 'handed_off' | 'in_progress'
  summary            TEXT,
  notes              TEXT,           -- freeform operator/agent notes
  artifacts          TEXT,           -- JSON array of files changed, services affected, etc
  started_at         TEXT DEFAULT (datetime('now')),
  ended_at           TEXT
);

CREATE TABLE task_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id     TEXT NOT NULL REFERENCES tasks(id),
  from_status TEXT,
  to_status   TEXT,
  actor       TEXT,
  note        TEXT,
  created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE feature_requests (
  id                 TEXT PRIMARY KEY,
  title              TEXT NOT NULL,
  kind               TEXT NOT NULL,         -- 'repetitive_work' | 'blocker' | 'guidance_gap'
  detail             TEXT NOT NULL,
  status             TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'resolved'
  task_id            TEXT REFERENCES tasks(id),
  session_id         TEXT REFERENCES sessions(id),
  agent_id           TEXT,
  model_name         TEXT,
  notes              TEXT,
  resolution         TEXT,                  -- 'discarded' | 'already_complete' | 'converted_to_task'
  resolution_task_id TEXT REFERENCES tasks(id),
  created_at         TEXT DEFAULT (datetime('now')),
  updated_at         TEXT DEFAULT (datetime('now'))
);
```

Session metadata is best-effort. The system should capture, when available:

- agent identifier (validated against `domain/providers.py` registry)
- model family + model version (validated as a pair; together derive `model_name`)
- operating mode
- rule set version
- instructions fingerprint
- freeform session reference
- skills used
- structured tool call summary
- separate token cost for producing/maintaining that tool call summary
- named design / architecture patterns
- decision notes
- theory notes
- started/ended timestamps
- token spend
- session notes

None of these optional fields should hard-fail a command if absent.

Why these belong on sessions, not tasks:

- the same task may be worked by different agents/models over time
- you want later analysis to compare runs, prompts, skills, and modes
- analytical framing is often session-specific even when the task stays the same

---

## Status Flow

```
IDEA → SCOPING → READY → IN_PROGRESS → REVIEW → DONE
                                     ↘ FAILED → READY  (if retry=true)
                                     ↘ BLOCKED
```

---

## Commands and Events

```python
# Commands
AddIdea(title, notes?)
ScopeTask(task_id, description, context, priority, depends_on?)
ClaimTask(agent_id, hint_filter?)
CompleteTask(task_id, summary, session_id?, artifacts?, tokens?)
FailTask(task_id, session_id, reason, retry?)
BlockTask(task_id, session_id, reason)
SplitTask(parent_id, subtasks[])
AddNote(task_id, note)
OpenSession(task_id, stage, agent_id, model_family?, model_version?, model_name?, operating_mode?, rule_set_version?, instructions_fingerprint?, session_ref?, skills_used?, tool_calls_summary?, tool_calls_summary_tokens?, design_patterns?, decision_notes?, theory_notes?, notes?)
CloseSession(session_id, outcome, summary?, tokens?, rule_set_version?, instructions_fingerprint?, skills_used?, tool_calls_summary?, tool_calls_summary_tokens?, design_patterns?, decision_notes?, theory_notes?, notes?)
LogTokens(session_id?, agent_id?, tokens_in, tokens_out, cache_read?, cache_write?, note?, replace?)
LogToolCallsSummary(session_id, tool_calls_summary, tokens?, note?)
SweepStaleSessions(cutoff_iso)
RequestFeature(title, kind, detail, task_id?, session_id?, agent_id?, model_name?, notes?)
ResolveFeatureRequest(feature_request_id, resolution, task_id?, note?)  # resolution: 'discarded' | 'already_complete' | 'converted_to_task'

# Events
IdeaAdded(task)
TaskScoped(task)
TaskClaimed(task, session)
ClaimFailed(reason)
TaskCompleted(task, sessions)
DependentsUnblocked(task_ids)
TaskFailed(task, session)
TaskRetried(task)
TaskBlocked(task, session)
TaskSplit(parent, children)
SessionOpened(session)
SessionClosed(session)
StaleSessionsSwept(sessions)
TokensLogged(session)
ToolCallsSummaryLogged(session)
FeatureRequested(feature_request)
FeatureRequestResolved(feature_request)
```

`CompleteTask` accepts `session_id` optionally. When provided, the
server validates `session.task_id == task_id` and refuses a mismatch
(this is what stops a `complete_task` for one task from orphaning
another task's open session). When omitted, every session for the task
that still has `ended_at IS NULL` is closed with the completion
summary; this is the drop-off recovery path. `TaskCompleted.sessions`
returns the list of sessions actually closed (possibly empty).

`OpenSession` auto-closes any prior open session for the same
`agent_id` with `outcome = "superseded"` before creating the new one.
This means a re-opened agent — same model, fresh conversation — heals
the prior session implicitly.

`SweepStaleSessions` is the time-bound floor: any session with
`started_at < cutoff_iso AND ended_at IS NULL` is closed with
`outcome = "abandoned"`. Catches the case where neither
`complete_task` nor a same-agent reopen ever arrives.

`QueueService.handle(command)` returns a list of events. All state transitions emit a corresponding `task_events` row recording the actor and an optional note.

---

## Business Logic Rules

- **`ClaimTask` must be atomic** — single `UPDATE ... RETURNING` in a transaction. Two agents must never claim the same task. Return `ClaimFailed` if nothing is claimable rather than raising.
- **`CompleteTask` must auto-unblock dependents** — after marking a task `DONE`, find any tasks whose entire `depends_on` list is now satisfied and promote them to `READY`, emitting `DependentsUnblocked`.
- **`SplitTask`** creates child tasks and sets the parent to `BLOCKED` until all children reach `DONE`.
- **`next_task`** (called internally by `ClaimTask`) selects the highest priority `READY` task where all dependencies are met, optionally filtered by `agent_hint`.
- **All token fields are optional on every call** — never error if omitted, default to 0.
- **Session metadata capture is best-effort** — store model, session reference,
  mode, rule provenance, skills, patterns, reasoning notes, timestamps, and
  token data whenever the caller provides them.
- **`tool_calls_summary` is structured session data** — store tool families or
  names with counts, not a prose description. Aliased names from the
  codex/claude-code split (`Bash`/`exec_command`, `queue_health`/`health`,
  …) are folded onto canonical keys at write-time so the stored summary
  is canonical at rest. `tool_calls_canonical()` still de-aliases at
  read-time as a back-compat path for legacy rows.
- **Agent / model identity is validated on session creation.** `agent_id`
  must be a known harness in `domain/providers.py`; `model_family` and
  `model_version`, if supplied, must be a registered pair. The
  `model_name` slug is derived as `{family}-{version}`. Unknown values
  raise `ValueError`. Adding a new harness or model family means
  appending a `ProviderAdapter` record to the registry.
- **Tool-call-summary token cost is separate from session token totals** — keep
  the overall session token fields as the source of truth for whole-session cost,
  and track `tool_calls_summary_tokens_*` separately for the cost of producing
  that summary itself.
- **`LogTokens` selectors and replace mode.** Exactly one of `session_id`
  or `agent_id` must be provided. `agent_id` resolves to the agent's
  currently-open session (open_session enforces one open session per
  agent). With `replace=True` the running totals are overwritten rather
  than added — for hooks/ingestors that re-read a full transcript or
  metric snapshot on each fire and want idempotent re-runs.
- **`get_task`** returns the task, its full session history, and a token rollup (sum of `tokens_in`, `tokens_out`, `tokens_cache_read`, `tokens_cache_write` across all sessions).
- **`RequestFeature`** is the path for "we should automate this", "I am
  blocked by missing capability", and "the repo/process is unclear". Treat it
  as a first-class record, not as a note on a task.
- **Task IDs** are short random slugs, e.g. `task_abc123`.

---

## MCP Tools

Defined in `server.py` only. Each tool dispatches to `QueueService` and returns the resulting events. No business logic in this layer.

```
add_idea(title, notes?)
scope_task(task_id, description, context, priority, depends_on?)
claim_task(agent_id, hint_filter?)
complete_task(task_id, session_id, summary, artifacts?, tokens?)
fail_task(task_id, session_id, reason, retry?)
block_task(task_id, session_id, reason)
split_task(parent_id, subtasks[])
add_note(task_id, note)
list_tasks(status?, agent_hint?)
health()
stats()
get_task(task_id)
open_session(task_id, stage, agent_id, model_name?, operating_mode?, rule_set_version?, instructions_fingerprint?, session_ref?, skills_used?, design_patterns?, decision_notes?, theory_notes?, notes?)
close_session(session_id, outcome, summary?, tokens?, rule_set_version?, instructions_fingerprint?, skills_used?, tool_calls_summary?, tool_calls_summary_tokens?, design_patterns?, decision_notes?, theory_notes?, notes?)
log_tokens(session_id?, agent_id?, tokens_in, tokens_out, cache_read?, cache_write?, note?, replace?)
log_tool_calls_summary(session_id, tool_calls_summary, tokens?, note?)
sweep_stale_sessions(max_age_hours?)
request_feature(title, kind, detail, task_id?, session_id?, agent_id?, model_name?, notes?)
resolve_feature_request(feature_request_id, resolution, task_id?, note?)
list_feature_requests(status?, kind?)
list_open_sessions()
list_session_notes(task_id?, since?)
agent_activity()
tool_calls_canonical()
```

---

## Tests

Tests run with `pytest` against `QueueService` using `InMemoryRepository`. No server, no database, no setup required. Cover at minimum:

- Claiming a task is atomic — a task claimed by agent_1 is not returned to agent_2
- Completing a task promotes newly unblocked dependents to `READY`
- `SplitTask` blocks the parent until all children are `DONE`
- `FailTask` with `retry=true` returns the task to `READY`
- Token rollup on `get_task` sums correctly across multiple sessions
- `ClaimTask` respects `hint_filter`
- `OpenSession` captures practical session metadata when supplied
- `CloseSession` merges added skills/patterns/analysis notes without losing the initial session context
- `RequestFeature` records repetition/blocker/guidance-gap requests with task/session context when present
- `health` returns a lightweight readiness/readability report for the queue backing store
- `stats` returns aggregate counts and token totals without requiring full task history reads
- `LogToolCallsSummary` records structured tool counts and separate summary-token cost

## Data Priorities

If callers only supply a subset, prioritize these first:

1. `agent_id`, `model_name`, `operating_mode`
2. `rule_set_version`, `instructions_fingerprint`
3. `started_at` / `ended_at`
4. token fields
5. `skills_used`
6. `tool_calls_summary`
7. `design_patterns`
8. `decision_notes`
9. `theory_notes`
10. general `notes`

This ordering is meant to maximize later analysis value while keeping the
capture burden reasonable.

---

## Configuration

- Expose on a configurable port, defaulting to `8483`
- Accept a `--db` flag for the database path, defaulting to `./queue.db`
- Run `schema.sql` automatically on first start if the database is absent
- No auth required

---

Start with `domain/` and get the tests green before touching `infra/` or `server.py`.
