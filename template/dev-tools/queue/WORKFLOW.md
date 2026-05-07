# queue workflow

This is the expected operating pattern for non-trivial work in this
repo.

Use the queue for:

- code or config edits
- multi-step investigation
- review and handoff
- repeated work, blockers, or missing guidance

You can skip it for:

- trivial read-only checks
- one-shot factual answers with no meaningful work record

## Minimum workflow

1. Confirm the queue is available with `health`
2. Try `claim_task`
3. If nothing suitable exists, create one with `add_idea` and
   `scope_task`
4. Start work with `open_session`
5. During work, record what is practical:
   - `add_note`
   - `log_tokens`
   - `log_tool_calls_summary`
   - `request_feature`
6. Pause with `close_session` at natural breaks (end of day,
   handoff, waiting on something). Keep the task itself in
   `in_progress` until the branch merges.
7. After merge, call `complete_task` with a summary and artifacts.
   Don't `complete_task` while the work still only lives on a
   feature branch.

## Expected metadata

Best-effort session metadata is the point of the system. If available,
capture:

- `agent_id`
- `model_name`
- `operating_mode`
- `rule_set_version`
- `instructions_fingerprint`
- `session_ref`
- `skills_used`
- `tool_calls_summary`
- `tool_calls_summary_tokens`
- `design_patterns`
- `decision_notes`
- `theory_notes`
- token usage
- freeform notes

Do not invent data just to fill fields. Omit what you do not know.

### `tool_calls_summary` shape

`tool_calls_summary` is a flat mapping of tool name (or tool family)
to an integer count, e.g.:

```json
{"Read": 12, "Edit": 3, "Bash": 7}
```

Nested objects aren't accepted — values must be integers. This
applies on `open_session`, `close_session`, and
`log_tool_calls_summary`. The token cost of producing the summary
itself goes on `tool_calls_summary_tokens` as a separate `TokenUsage`
and does not feed session-level token totals.

Aliased tool names from the codex/claude-code split (e.g. `Bash`
vs `exec_command`, `queue_health` vs `health`) get folded onto a
single canonical key at write-time — the stored summary is canonical
at rest. Pass whatever the agent natively reports; the queue handles
the dedup. Unknown names pass through unchanged.

### `log_tokens` selectors and `replace` mode

`log_tokens` accepts either `session_id` or `agent_id` — pass the one
you have. `agent_id` resolves to the agent's currently-open session,
which is the right form for harness hooks and ingestion pipelines.

`replace=True` overwrites the session's running totals instead of
adding. Use this when the caller computes the running total on each
fire (e.g. an OTel ingestor reading a metric snapshot, or a hook
summing the full transcript) and wants re-firing to be idempotent.
Default is `replace=False` — additive — for callers that supply a
delta.

## Feature requests

Use `request_feature` when:

- you are repeating the same task often
- a missing capability blocks progress
- the repo or process is unclear enough to slow work down

Kinds:

- `repetitive_work`
- `blocker`
- `guidance_gap`

### Resolving feature requests

Close a feature request with `resolve_feature_request`. Pick one of:

- `discarded` — won't fix, no longer applicable, or out of scope.
- `already_complete` — the issue was addressed elsewhere (e.g. by
  unrelated work) without ever being explicitly tracked.
- `converted_to_task` — the request is now real work; create the task
  first (`add_idea` + `scope_task`) and pass the new `task_id`. The
  link is stored on `resolution_task_id` so it stays distinct from the
  `task_id` recorded when the FR was raised.

`note` is optional but encouraged: it's appended to the FR's `notes`
and is the only place the rationale lives once the row is closed.

## End-of-task hygiene

Before handoff or opening a PR:

- close any open session (`close_session`)
- make sure the task summary is accurate
- mention the queue task ID in the handoff or PR when relevant
- mention if queue usage was intentionally skipped, and why

Leave the task itself in `in_progress` until the branch is merged.
Call `complete_task` only after merge. If the session needed to
close before merge, open a fresh session on the task afterwards to
record the completion — don't treat PR-open as done.

Subtle gotcha: `complete_task` also closes the session you pass
with it. If you complete a task while a session for a *different*
task is still open, close that other session first — otherwise it
ends up orphaned (this is the failure mode that produced the stale
opens swept by `task_4ealgq`). When in doubt, call the
`list_open_sessions` MCP tool to see exactly which sessions are
live, or run
`uv run --directory dev-tools/queue python list_open_sessions.py`
when the MCP server isn't reachable.

## Visibility queries

Read-only MCP tools surface what the queue already captures:

- `list_open_sessions` — sessions still open, with task title/status
- `list_session_notes` — sessions carrying decision/theory notes or
  design patterns; filter by `task_id` and/or ISO `since`
- `agent_activity` — per-agent breakdown of sessions, tokens, tool calls
- `tool_calls_canonical` — tool-call totals deduplicated under
  canonical names

Use these for retros and "where did the project's effort go"
questions without scraping `get_task` per task.

## Client registration

Example client configs live in [`examples/`](./examples/):

- [`generic-stdio-uv.json`](./examples/generic-stdio-uv.json)
- [`generic-stdio-venv.json`](./examples/generic-stdio-venv.json)

## Langfuse Stop hook (queue-aware)

The queue ships a vendored copy of doneyli's Langfuse Stop hook with a
queue-context resolver layered on top:
[`hooks/langfuse_hook.py`](./hooks/langfuse_hook.py). When the hook
fires after each Claude Code turn, it tags the resulting Langfuse trace
with the queue session/task IDs the turn belongs to and sets
Langfuse's native `session_id` so all turns of one queue session
collapse into one Langfuse session timeline. Contract pinned in
[`hooks/LANGFUSE_HOOK_DESIGN.md`](./hooks/LANGFUSE_HOOK_DESIGN.md).

ID resolution is per-field, env wins:

1. `CELL_QUEUE_SESSION_ID` / `CELL_QUEUE_TASK_ID` env vars,
   tagged `source = "env"`. Operator-explicit; load-bearing.
2. Fallback: read `$CELL_QUEUE_DB` and pick the most recent open
   session for `agent_id="claude-code"`. Yields both ids together,
   tagged `source = "db"`. Best-effort; valid as long as the
   one-open-session-per-agent invariant holds.
3. Missing or unreadable inputs leave the corresponding tag absent;
   the hook still produces a Langfuse trace, just untagged.

Each resolved ID carries its source as a separate metadata key
(`queue_session_id_source`, `queue_task_id_source`),
so an operator auditing traces in Langfuse can distinguish operator-
pinned from auto-resolved.

### Operator install

Stand up Langfuse via the doneyli template
([`docker compose up`](https://github.com/doneyli/claude-code-langfuse-template)
in their repo), then point Claude Code at our hook in
`~/.claude/settings.json`:

```jsonc
{
  "env": {
    "TRACE_TO_LANGFUSE": "true",
    "LANGFUSE_HOST": "http://localhost:3050",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-...",
    "LANGFUSE_SECRET_KEY": "sk-lf-...",
    "CELL_QUEUE_DB": "/abs/path/to/dev-tools/queue/queue.db"
    // Optional: pin the queue context explicitly (sets source=env).
    // "CELL_QUEUE_SESSION_ID": "session_xxx",
    // "CELL_QUEUE_TASK_ID":    "task_xxx"
  },
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "uv run --with 'langfuse>=3.0,<4.0' --python 3.12 /abs/path/to/dev-tools/queue/hooks/langfuse_hook.py"
      }]
    }]
  }
}
```

Skip doneyli's `./scripts/install-hook.sh` — that path installs the
upstream hook, which doesn't know about the queue.

### What's still manual

The Stop hook writes to Langfuse, **not** to the queue's session rows
(`tokens_in`, `tokens_out`, `tool_calls_summary`, …). Closing
`fr_wtck0w` so those rollups auto-populate is a future change to the
same hook — ~5 lines that call `log_tokens(agent_id="claude-code",
replace=True, …)` against the queue alongside the Langfuse submission.
Until then, manual `log_tokens` / `log_tool_calls_summary` is the way
to populate session rows.
