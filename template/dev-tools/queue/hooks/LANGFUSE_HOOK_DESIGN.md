# Langfuse hook — design

Status: **design**, not implemented.
Refs `task_s7ojxg` (the auto-token-capture half stays scoped out — see
[Non-goals](#non-goals-v1)).

This doc pins the contract before the hook lands. Read end-to-end before
reviewing the code.

---

## Goal

Tag Claude Code's Langfuse traces with the queue session and
task IDs they belong to, so the operator can pivot between queue tasks
and Langfuse traces in either direction. Achieved by vendoring a
modified copy of the Stop hook from
[`doneyli/claude-code-langfuse-template`](https://github.com/doneyli/claude-code-langfuse-template)
and adding ID resolution + tagging at the top of the file.

## Non-goals (v1)

- **Auto-populating queue session token rollups.** `fr_wtck0w` stays
  open after this v1; manual `log_tokens` / `log_tool_calls_summary`
  remain authoritative for `sessions.tokens_*` and
  `sessions.tool_calls_summary` columns. When we want to close
  fr_wtck0w, the same hook can call
  `log_tokens(agent_id="claude-code", replace=True, …)` against the
  queue — ~5 extra lines.
- **OTel receiver inside the queue.** The earlier `OTEL_DESIGN.md`
  (PR #38, closed) sketched this; the hook-only path is enough for the
  local-PC v1 the operator wants.
- **Forking doneyli upstream.** We vendor a copy under
  `dev-tools/queue/hooks/` and document our copy as the one to
  install. Upstream PR is a future option, not on the critical path.

## Architecture

Claude Code fires the Stop hook after each assistant turn. Our hook,
invoked there, owes its core (transcript parsing, Langfuse SDK calls)
to doneyli's upstream — additions are confined to the top of the file:

1. Resolve queue context (env first, queue.db second, neither = absent).
2. Run doneyli's existing logic to build the Langfuse trace.
3. Before submitting the trace, attach queue context as metadata
   (session_id, task_id, plus a per-field source tag) and set
   Langfuse's native `session_id` to the queue session_id.

The hook never errors out the agent. If Langfuse is unreachable,
doneyli's existing local-queue resilience kicks in. If queue.db is
unreachable or no open session matches, the trace is still produced —
just untagged.

## ID resolution

Per-field, env wins:

1. `CELL_QUEUE_SESSION_ID` env var → use, source = `env`.
2. Else: read `$CELL_QUEUE_DB`, take the most recent open session
   with `agent_id="claude-code"`. Yields both the session_id and the
   task_id it's attached to. Source = `db`.
3. Else: ID absent.

`CELL_QUEUE_TASK_ID` resolves the same way:

1. Env var → source = `env`.
2. Else: take the task_id from the session row resolved in (1)/(2)
   above. Source = `db`.
3. Else: absent.

The fields are independent, so an operator can pin one ID via env
(e.g. session_id) while letting the other resolve from db. The source
tag makes that combination legible after the fact.

## Tagging contract

Attached to every Langfuse trace the hook creates per turn (via the
SDK's `metadata` dict on `trace()`):

| Metadata key                          | Type      | When present                              |
|---------------------------------------|-----------|-------------------------------------------|
| `queue_session_id`            | string    | Session resolved (env or db)              |
| `queue_session_id_source`     | `env`/`db`| Always when `_session_id` is set          |
| `queue_task_id`               | string    | Task resolved (env or db)                 |
| `queue_task_id_source`        | `env`/`db`| Always when `_task_id` is set             |

Plus, when a session_id resolves: set Langfuse's native `session_id`
field on the trace to the queue session_id. This makes Langfuse's
session view group all turns of one queue session into a single
collapsed timeline. Without the queue session_id, fall back to
whatever doneyli's upstream uses (Claude Code's own session id).

The per-field source tag matters because the two resolution paths
have different reliability characteristics:

- `env` — operator-explicit. Load-bearing if set.
- `db` — best-effort heuristic. Valid as long as the
  one-open-session-per-agent invariant holds; wrong if the operator
  runs multiple Claude Code instances against one queue.db without
  pinning each via env.

## File layout

```
dev-tools/queue/hooks/
├── LANGFUSE_HOOK_DESIGN.md       (this doc)
├── langfuse_hook.py              (vendored from doneyli + extended)
└── (tests live under existing dev-tools/queue/tests/)
```

Doneyli is MIT-licensed; we copy the LICENSE header into our hook and
credit upstream.

The hook runs via `uv run --with 'langfuse>=3.0,<4.0'` per doneyli's
pattern, so `langfuse` doesn't have to be added to the queue's
project venv.

Tests stub the Langfuse SDK and the queue.db lookup, exercising:

- env-sourced IDs winning over db
- db-sourced IDs when env is unset
- mixed (env session_id + db task_id, and vice versa)
- both absent → trace still created, no queue metadata, no source tags
- queue.db unreachable → trace still created untagged
- queue.db present but no open session → trace still created untagged

## Operator install

```jsonc
// ~/.claude/settings.json
{
  "env": {
    "TRACE_TO_LANGFUSE": "true",
    "LANGFUSE_HOST": "http://localhost:3050",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-...",
    "LANGFUSE_SECRET_KEY": "sk-lf-...",
    "CELL_QUEUE_DB": "/home/operator/.../dev-tools/queue/queue.db"
    // Optional: pin the queue context explicitly (sets the `env` source tag).
    // "CELL_QUEUE_SESSION_ID": "session_xxx",
    // "CELL_QUEUE_TASK_ID":    "task_xxx"
  },
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "uv run --with 'langfuse>=3.0,<4.0' --python 3.12 /path/to/dev-tools/queue/hooks/langfuse_hook.py"
      }]
    }]
  }
}
```

doneyli's `./scripts/install-hook.sh` is **not** used; that path
installs the upstream hook, which doesn't know about the queue.

## Open questions

1. **Vendor strategy.** Verbatim copy + diff at the top, or a thin
   wrapper that imports from doneyli? Verbatim is simpler and removes
   the import-from-vendored-tree problem; re-vendor manually when
   doneyli ships a meaningful upstream change. Lean verbatim.
2. **Multi-instance attribution.** db-sourced lookup picks the
   most recently opened session. With two Claude Code instances
   running, the older one gets tagged with the newer one's session id.
   Document the env-var-pinning recommendation; don't engineer beyond
   it for v1.
3. **Path to closing fr_wtck0w later.** Once we want queue session
   rows to auto-populate, the same hook adds a `log_tokens` call
   alongside the Langfuse trace submission. Out of v1 because the user
   value (Langfuse correlation) is independent.
