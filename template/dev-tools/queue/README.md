# queue

A task queue as an MCP server. Tracks ideas, scoping, execution,
review, token usage, and cross-task dependencies. Intended to run
locally alongside an MCP-aware client (Claude Code, Cursor, etc.)
and be registered as a tool source.

The queue is also intended to support later analysis of agent behavior:
which model ran, which skills it used, what patterns it believed it was
applying, what reasoning/theory it cited while making decisions, and
which rules/instructions bundle it was operating under.

Spec: [`SPEC.md`](./SPEC.md).
Operator workflow: [`WORKFLOW.md`](./WORKFLOW.md).

## Status

**Domain + SQLite + MCP server implemented.** The queue core now exists:

- models, commands, events
- `QueueService`
- spec-driven tests against an in-memory repository
- `SQLiteRepository` plus `schema.sql`
- session metadata capture for agent/model/token/timestamp notes
- session metadata capture for skills, design patterns, decision notes,
  theory notes, and operating mode
- session provenance capture for `rule_set_version` and
  `instructions_fingerprint`
- structured `tool_calls_summary` capture with separate token accounting
- feature-request capture for repetition, blockers, and guidance gaps
- FastMCP server dispatch in `server.py`

## Layout

```
dev-tools/queue/
├── README.md
├── pyproject.toml
├── domain/            # pure Python: models, commands, events, service
├── infra/             # SQLiteRepository + schema.sql
├── tests/             # pytest suite; runs against InMemoryRepository
└── server.py          # fastmcp dispatch (added in a later PR)
```

## Running the tests

```sh
cd dev-tools/queue
uv sync
uv run pytest
```

Current coverage includes:

- claiming a task only once
- unblocking dependents when prerequisites complete
- split parent/child behavior
- retry flow after failure
- token rollup across sessions
- `agent_hint` claim filtering
- queue `health` and `stats` read models
- structured tool-call summary capture with separate summary-token totals
- SQLite round-trip coverage for tasks, sessions, task events, and
  feature requests
- FastMCP tool dispatch coverage against a real SQLite-backed app
- stdio end-to-end coverage through a launched MCP server process

## Running the server

HTTP transport on the default local port:

```sh
cd dev-tools/queue
uv run python server.py --db ./queue.db --transport http --host 127.0.0.1 --port 8483
```

stdio transport for MCP clients that launch the process directly:

```sh
cd dev-tools/queue
uv run python server.py --db ./queue.db --transport stdio
```

## Example Client Registration

Copy-pasteable examples also live under [`examples/`](./examples/).

A generic stdio MCP registration looks like this:

```json
{
  "mcpServers": {
    "queue": {
      "command": "<absolute-path-to-cell>/dev-tools/queue/.venv/bin/python",
      "args": [
        "<absolute-path-to-cell>/dev-tools/queue/server.py",
        "--db",
        "<absolute-path-to-cell>/dev-tools/queue/queue.db",
        "--transport",
        "stdio"
      ]
    }
  }
}
```

If your client launches through `uv`, the equivalent command shape is:

```json
{
  "mcpServers": {
    "queue": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "<absolute-path-to-cell>/dev-tools/queue",
        "python",
        "server.py",
        "--db",
        "./queue.db",
        "--transport",
        "stdio"
      ]
    }
  }
}
```

Use the direct venv Python form if you want the most deterministic launch
path. Use the `uv` form if that matches how your MCP client normally boots
project-local tools.

Both examples use absolute paths (or `uv run --directory`) rather than a
`cwd` field on the server entry. Not every MCP client honors `cwd`
(Claude Code, for example, ignores it on project-scoped `.mcp.json`),
so relying on it means the server works in one client and silently
fails to launch in another.

Implemented MCP tools:

- `add_idea`
- `scope_task`
- `claim_task`
- `complete_task`
- `fail_task`
- `block_task`
- `split_task`
- `add_note`
- `list_tasks`
- `health`
- `stats`
- `get_task`
- `open_session`
- `close_session`
- `log_tokens`
- `log_tool_calls_summary`
- `request_feature`
- `list_feature_requests`
- `sweep_stale_sessions`
- `list_open_sessions` — open sessions joined to task title/status
- `list_session_notes` — sessions carrying decision/theory notes or
  design patterns; supports `task_id` and ISO `since` filters
- `agent_activity` — per-agent breakdown of sessions, tokens, tool calls
- `tool_calls_canonical` — collapsed tool-call totals under canonical
  names (the codex/claude alias bifurcation deduplicated)

### Shapes worth knowing

- `tool_calls_summary` (accepted by `open_session`, `close_session`,
  `log_tool_calls_summary`) is a flat `{tool_name: int}` map, e.g.
  `{"Read": 12, "Edit": 3}`. Nested objects aren't accepted — values
  must be integers.
- Token fields (`tokens`, `tool_calls_summary_tokens`) take a flat
  object with `tokens_in`, `tokens_out`, `cache_read`, `cache_write`
  integer keys; all are optional and default to 0.

### Task vs. session closure

`close_session` ends a unit of work on a task; `complete_task`
marks the task itself `done`. Close sessions at natural breaks,
but only call `complete_task` after the work has merged to `main` —
don't mark a task `done` while it still only lives on a feature
branch. If you need to pause before merge, close the session with
`outcome=handed_off` and open a fresh session after merge to
record the completion. Details in
[`WORKFLOW.md`](./WORKFLOW.md#end-of-task-hygiene).
