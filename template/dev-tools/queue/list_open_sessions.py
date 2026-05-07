"""List currently-open queue sessions, with task context.

Read-only audit utility. The ``stats`` MCP tool exposes only a count
(``open_session_count``); this script lets the operator see *which*
sessions are open and which task each belongs to, so stale ones can
be closed before they distort visibility tooling.

Usage:

    uv run --directory dev-tools/queue python list_open_sessions.py

Or, if the queue venv is already on ``$PATH``:

    python dev-tools/queue/list_open_sessions.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

QUEUE_DB = Path(__file__).resolve().parent / "queue.db"


def list_open_sessions(db_path: Path = QUEUE_DB) -> int:
    if not db_path.is_file():
        raise SystemExit(f"queue.db not found at {db_path}")

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.id, s.agent_id, s.stage, s.started_at,
                   s.task_id, t.title, t.status
            FROM sessions s
            LEFT JOIN tasks t ON s.task_id = t.id
            WHERE s.ended_at IS NULL
            ORDER BY s.started_at
            """
        )
        rows = cur.fetchall()

    if not rows:
        print("No open sessions.")
        return 0

    print(f"{len(rows)} open session(s):\n")
    for sid, agent, stage, started, task_id, title, task_status in rows:
        print(f"  {sid}")
        print(f"    started: {started}")
        print(f"    agent:   {agent}")
        print(f"    stage:   {stage}")
        print(f"    task:    {task_id} ({task_status}) — {title}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(list_open_sessions())
