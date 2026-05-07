"""Tests for the queue-aware Langfuse hook resolver.

Covers ``resolve_queue_context()``: env wins per-field, db fallback,
mixed sourcing, missing config, db unreachable, db-with-no-open-session.
The hook's transcript parsing + Langfuse SDK calls are upstream from
doneyli; this file only exercises our additions, since those are the
parts the project owns. Plus a static AST regression test that pins
every ``create_trace()`` call site to pass ``queue_context``, since the
upstream code path forks across two call sites in process_transcript
(loop-body and final-turn) and missing the second was a real bug.
"""

from __future__ import annotations

import ast
import importlib.util
import sqlite3
import sys
from pathlib import Path
from typing import Iterator

import pytest

HOOK_PATH = Path(__file__).resolve().parents[1] / "hooks" / "langfuse_hook.py"


@pytest.fixture
def hook_module(monkeypatch):
    """Load hooks/langfuse_hook.py without executing main().

    The upstream file imports `langfuse` at top level. Tests stub it out
    with a sentinel module before import, since the resolver doesn't
    touch the Langfuse SDK.
    """
    fake_langfuse = type(sys)("langfuse")
    fake_langfuse.Langfuse = object  # any attribute that exists
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse)

    spec = importlib.util.spec_from_file_location("_test_langfuse_hook", HOOK_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def queue_db(tmp_path) -> Path:
    """Build a queue.db with the queue schema's ``sessions`` columns
    that the resolver reads. We don't need the full domain schema — only
    the fields the resolver SELECTs."""
    path = tmp_path / "queue.db"
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE sessions (
                id          TEXT PRIMARY KEY,
                task_id     TEXT,
                agent_id    TEXT,
                started_at  TEXT,
                ended_at    TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    return path


def _insert_session(
    db: Path,
    *,
    id: str,
    task_id: str,
    agent_id: str,
    started_at: str,
    ended_at: str | None = None,
) -> None:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO sessions (id, task_id, agent_id, started_at, ended_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (id, task_id, agent_id, started_at, ended_at),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def clean_env(monkeypatch) -> Iterator[None]:
    for var in (
        "CELL_QUEUE_SESSION_ID",
        "CELL_QUEUE_TASK_ID",
        "CELL_QUEUE_DB",
    ):
        monkeypatch.delenv(var, raising=False)
    yield


def test_env_vars_win_when_both_set(hook_module, monkeypatch, clean_env, queue_db):
    """Env-set IDs are tagged source=env, regardless of what's in db."""
    _insert_session(
        queue_db,
        id="session_db",
        task_id="task_db",
        agent_id="claude-code",
        started_at="2026-04-27T12:00:00+00:00",
    )
    monkeypatch.setenv("CELL_QUEUE_SESSION_ID", "session_env")
    monkeypatch.setenv("CELL_QUEUE_TASK_ID", "task_env")
    monkeypatch.setenv("CELL_QUEUE_DB", str(queue_db))

    out = hook_module.resolve_queue_context()

    assert out == {
        "queue_session_id": "session_env",
        "queue_session_id_source": "env",
        "queue_task_id": "task_env",
        "queue_task_id_source": "env",
    }


def test_db_fallback_when_env_unset(hook_module, monkeypatch, clean_env, queue_db):
    _insert_session(
        queue_db,
        id="session_db",
        task_id="task_db",
        agent_id="claude-code",
        started_at="2026-04-27T12:00:00+00:00",
    )
    monkeypatch.setenv("CELL_QUEUE_DB", str(queue_db))

    out = hook_module.resolve_queue_context()

    assert out == {
        "queue_session_id": "session_db",
        "queue_session_id_source": "db",
        "queue_task_id": "task_db",
        "queue_task_id_source": "db",
    }


def test_mixed_env_session_db_task(hook_module, monkeypatch, clean_env, queue_db):
    """Per-field resolution: env session_id + db task_id is a valid combo."""
    _insert_session(
        queue_db,
        id="session_db",
        task_id="task_db",
        agent_id="claude-code",
        started_at="2026-04-27T12:00:00+00:00",
    )
    monkeypatch.setenv("CELL_QUEUE_SESSION_ID", "session_env")
    monkeypatch.setenv("CELL_QUEUE_DB", str(queue_db))

    out = hook_module.resolve_queue_context()

    assert out["queue_session_id"] == "session_env"
    assert out["queue_session_id_source"] == "env"
    assert out["queue_task_id"] == "task_db"
    assert out["queue_task_id_source"] == "db"


def test_picks_most_recently_started_open_session(
    hook_module, monkeypatch, clean_env, queue_db
):
    """Multi-instance attribution: last-opened wins. Tested explicitly so
    the LIMIT-1 ORDER BY contract is locked, not accidental."""
    _insert_session(
        queue_db,
        id="session_old",
        task_id="task_old",
        agent_id="claude-code",
        started_at="2026-04-27T10:00:00+00:00",
    )
    _insert_session(
        queue_db,
        id="session_new",
        task_id="task_new",
        agent_id="claude-code",
        started_at="2026-04-27T13:00:00+00:00",
    )
    monkeypatch.setenv("CELL_QUEUE_DB", str(queue_db))

    out = hook_module.resolve_queue_context()

    assert out["queue_session_id"] == "session_new"
    assert out["queue_task_id"] == "task_new"


def test_skips_closed_sessions(hook_module, monkeypatch, clean_env, queue_db):
    _insert_session(
        queue_db,
        id="session_closed",
        task_id="task_closed",
        agent_id="claude-code",
        started_at="2026-04-27T13:00:00+00:00",
        ended_at="2026-04-27T13:30:00+00:00",
    )
    _insert_session(
        queue_db,
        id="session_open",
        task_id="task_open",
        agent_id="claude-code",
        started_at="2026-04-27T10:00:00+00:00",
    )
    monkeypatch.setenv("CELL_QUEUE_DB", str(queue_db))

    out = hook_module.resolve_queue_context()

    assert out["queue_session_id"] == "session_open"


def test_skips_other_agents(hook_module, monkeypatch, clean_env, queue_db):
    _insert_session(
        queue_db,
        id="session_codex",
        task_id="task_codex",
        agent_id="codex",
        started_at="2026-04-27T13:00:00+00:00",
    )
    monkeypatch.setenv("CELL_QUEUE_DB", str(queue_db))

    out = hook_module.resolve_queue_context()

    assert out == {}


def test_no_env_no_db_returns_empty(hook_module, clean_env):
    assert hook_module.resolve_queue_context() == {}


def test_db_path_set_but_file_missing(hook_module, monkeypatch, clean_env, tmp_path):
    monkeypatch.setenv("CELL_QUEUE_DB", str(tmp_path / "absent.db"))

    assert hook_module.resolve_queue_context() == {}


def test_db_unreadable_returns_empty(hook_module, monkeypatch, clean_env, tmp_path):
    """Garbled file at the DB path: hook never errors, returns empty."""
    bad_db = tmp_path / "garbage.db"
    bad_db.write_bytes(b"this is not a sqlite database file")
    monkeypatch.setenv("CELL_QUEUE_DB", str(bad_db))

    assert hook_module.resolve_queue_context() == {}


def test_db_present_no_open_session(hook_module, monkeypatch, clean_env, queue_db):
    """DB exists, schema present, but no open session: empty resolution."""
    monkeypatch.setenv("CELL_QUEUE_DB", str(queue_db))

    assert hook_module.resolve_queue_context() == {}


def test_env_partial_session_only(hook_module, monkeypatch, clean_env):
    """Operator pinned just session_id; no DB → task_id stays absent."""
    monkeypatch.setenv("CELL_QUEUE_SESSION_ID", "session_pinned")

    out = hook_module.resolve_queue_context()

    assert out == {
        "queue_session_id": "session_pinned",
        "queue_session_id_source": "env",
    }


def test_env_partial_task_only_with_db_session(
    hook_module, monkeypatch, clean_env, queue_db
):
    """Operator pinned task_id; session_id resolves from db."""
    _insert_session(
        queue_db,
        id="session_db",
        task_id="task_db_ignored",
        agent_id="claude-code",
        started_at="2026-04-27T12:00:00+00:00",
    )
    monkeypatch.setenv("CELL_QUEUE_TASK_ID", "task_pinned")
    monkeypatch.setenv("CELL_QUEUE_DB", str(queue_db))

    out = hook_module.resolve_queue_context()

    assert out["queue_session_id"] == "session_db"
    assert out["queue_session_id_source"] == "db"
    assert out["queue_task_id"] == "task_pinned"
    assert out["queue_task_id_source"] == "env"


# ---------- regression: every create_trace call site passes queue_context ----------


def _create_trace_call_sites(tree: ast.AST) -> list[ast.Call]:
    """All ast.Call nodes in the file that invoke create_trace by name."""
    sites: list[ast.Call] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "create_trace"
        ):
            sites.append(node)
    return sites


def test_every_create_trace_call_passes_queue_context():
    """The hook has create_trace calls in (a) process_transcript's
    inline-turn handling, (b) process_transcript's final-turn handling,
    and (c) drain_queue. Missing queue_context on any of them produces
    untagged Langfuse traces — exactly the bug this regression test
    pins down. Verified statically via AST so the check costs nothing
    and doesn't need the langfuse SDK."""
    tree = ast.parse(HOOK_PATH.read_text())
    sites = _create_trace_call_sites(tree)
    # We expect at least 3 call sites; if the hook gets refactored to
    # collapse them, that's fine — the assertion below still holds for
    # whatever count remains.
    assert len(sites) >= 3, (
        f"expected at least 3 create_trace call sites, found {len(sites)}"
    )
    missing: list[int] = []
    for call in sites:
        kwargs = {kw.arg for kw in call.keywords if kw.arg is not None}
        if "queue_context" not in kwargs:
            missing.append(call.lineno)
    assert not missing, (
        f"create_trace calls missing queue_context kwarg at lines: {missing}"
    )


# ---------- queue token writeback (closes fr_wtck0w) ----------


def test_sum_assistant_token_usage_sums_across_messages(hook_module):
    msgs = [
        {
            "type": "assistant",
            "message": {
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 40,
                    "cache_read_input_tokens": 20,
                    "cache_creation_input_tokens": 10,
                }
            },
        },
        {
            "type": "assistant",
            "message": {"usage": {"input_tokens": 50, "output_tokens": 12}},
        },
    ]
    assert hook_module.sum_assistant_token_usage(msgs) == {
        "tokens_in": 150,
        "tokens_out": 52,
        "tokens_cache_read": 20,
        "tokens_cache_write": 10,
    }


def test_sum_assistant_token_usage_handles_missing_usage(hook_module):
    """Some assistant parts (e.g. tool_use deltas) carry no usage block.
    Skip them silently — never raise."""
    msgs = [
        {"type": "assistant", "message": {}},  # no usage at all
        {"type": "assistant"},  # no message dict
        "not a dict",  # bogus payload
        {
            "type": "assistant",
            "message": {"usage": {"input_tokens": 7, "output_tokens": 3}},
        },
    ]
    assert hook_module.sum_assistant_token_usage(msgs) == {
        "tokens_in": 7,
        "tokens_out": 3,
        "tokens_cache_read": 0,
        "tokens_cache_write": 0,
    }


def _open_session(db: Path, session_id: str = "session_open") -> str:
    """Insert one open session row and return its id."""
    _insert_session(
        db,
        id=session_id,
        task_id="task_xyz",
        agent_id="claude-code",
        started_at="2026-04-27T12:00:00+00:00",
    )
    return session_id


def _read_session_tokens(db: Path, session_id: str) -> tuple[int, int, int, int]:
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT tokens_in, tokens_out, tokens_cache_read, tokens_cache_write "
            "FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    return tuple(row)  # type: ignore[return-value]


@pytest.fixture
def queue_db_with_tokens(tmp_path) -> Path:
    """Variant of queue_db that includes the token columns the writeback
    hits."""
    path = tmp_path / "queue.db"
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE sessions (
                id                  TEXT PRIMARY KEY,
                task_id             TEXT,
                agent_id            TEXT,
                started_at          TEXT,
                ended_at            TEXT,
                tokens_in           INTEGER DEFAULT 0,
                tokens_out          INTEGER DEFAULT 0,
                tokens_cache_read   INTEGER DEFAULT 0,
                tokens_cache_write  INTEGER DEFAULT 0
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    return path


def test_add_session_tokens_to_queue_adds_deltas_to_open_session(
    hook_module, monkeypatch, clean_env, queue_db_with_tokens
):
    sid = _open_session(queue_db_with_tokens)
    monkeypatch.setenv("CELL_QUEUE_DB", str(queue_db_with_tokens))

    hook_module.add_session_tokens_to_queue(
        sid,
        {
            "tokens_in": 100,
            "tokens_out": 40,
            "tokens_cache_read": 5,
            "tokens_cache_write": 2,
        },
    )
    hook_module.add_session_tokens_to_queue(
        sid,
        {
            "tokens_in": 50,
            "tokens_out": 12,
            "tokens_cache_read": 0,
            "tokens_cache_write": 0,
        },
    )

    assert _read_session_tokens(queue_db_with_tokens, sid) == (150, 52, 5, 2)


def test_add_session_tokens_to_queue_skips_closed_sessions(
    hook_module, monkeypatch, clean_env, queue_db_with_tokens
):
    """Tokens for an ended session are dropped — UPDATE's WHERE clause
    filters on ended_at IS NULL. Avoids tokens leaking to tasks after
    they're complete."""
    _insert_session(
        queue_db_with_tokens,
        id="session_closed",
        task_id="task_done",
        agent_id="claude-code",
        started_at="2026-04-27T11:00:00+00:00",
        ended_at="2026-04-27T11:30:00+00:00",
    )
    monkeypatch.setenv("CELL_QUEUE_DB", str(queue_db_with_tokens))

    hook_module.add_session_tokens_to_queue(
        "session_closed",
        {
            "tokens_in": 1000,
            "tokens_out": 500,
            "tokens_cache_read": 0,
            "tokens_cache_write": 0,
        },
    )

    assert _read_session_tokens(queue_db_with_tokens, "session_closed") == (
        0,
        0,
        0,
        0,
    )


def test_add_session_tokens_to_queue_no_session_id_is_noop(
    hook_module, monkeypatch, clean_env, queue_db_with_tokens
):
    sid = _open_session(queue_db_with_tokens)
    monkeypatch.setenv("CELL_QUEUE_DB", str(queue_db_with_tokens))

    hook_module.add_session_tokens_to_queue(
        "",
        {
            "tokens_in": 100,
            "tokens_out": 40,
            "tokens_cache_read": 0,
            "tokens_cache_write": 0,
        },
    )

    assert _read_session_tokens(queue_db_with_tokens, sid) == (0, 0, 0, 0)


def test_add_session_tokens_to_queue_zero_totals_is_noop(
    hook_module, monkeypatch, clean_env, queue_db_with_tokens
):
    """No round-trip to SQLite when there's nothing to add."""
    sid = _open_session(queue_db_with_tokens)
    monkeypatch.setenv("CELL_QUEUE_DB", str(queue_db_with_tokens))

    hook_module.add_session_tokens_to_queue(
        sid,
        {
            "tokens_in": 0,
            "tokens_out": 0,
            "tokens_cache_read": 0,
            "tokens_cache_write": 0,
        },
    )

    assert _read_session_tokens(queue_db_with_tokens, sid) == (0, 0, 0, 0)


def test_add_session_tokens_to_queue_db_unreachable(
    hook_module, monkeypatch, clean_env, tmp_path
):
    """Bad DB path must not raise — hook never errors out the agent."""
    monkeypatch.setenv("CELL_QUEUE_DB", str(tmp_path / "absent.db"))
    hook_module.add_session_tokens_to_queue(
        "session_anything",
        {
            "tokens_in": 1,
            "tokens_out": 1,
            "tokens_cache_read": 0,
            "tokens_cache_write": 0,
        },
    )  # no exception
