from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from typing import Any, cast

from fastmcp import FastMCP

from datetime import UTC, datetime, timedelta

from domain.commands import (
    AddIdea,
    AddNote,
    BlockTask,
    ClaimTask,
    CloseSession,
    CompleteTask,
    FailTask,
    LogToolCallsSummary,
    LogTokens,
    OpenSession,
    RequestFeature,
    ResolveFeatureRequest,
    ScopeTask,
    SplitTask,
    SubtaskInput,
    SweepStaleSessions,
)
from domain.models import TokenUsage
from domain.queue import QueueService
from infra.repository import SQLiteRepository


def create_service(db_path: str = "./queue.db") -> QueueService:
    repository = SQLiteRepository.connect(db_path)
    return QueueService(repository=repository)


def create_app(db_path: str = "./queue.db") -> FastMCP:
    service = create_service(db_path)
    app = FastMCP(
        name="queue",
        instructions=(
            "Task queue for cell agents. Use it to track ideas, sessions, "
            "token usage, dependencies, and feature requests."
        ),
    )

    @app.tool()
    def add_idea(title: str, notes: str | None = None) -> list[dict[str, Any]]:
        return _serialize_events(service.handle(AddIdea(title=title, notes=notes)))

    @app.tool()
    def scope_task(
        task_id: str,
        description: str,
        context: str,
        priority: int,
        depends_on: list[str] | None = None,
        relevant_files: list[str] | None = None,
        relevant_services: list[str] | None = None,
        agent_hint: str | None = None,
    ) -> list[dict[str, Any]]:
        return _serialize_events(
            service.handle(
                ScopeTask(
                    task_id=task_id,
                    description=description,
                    context=context,
                    priority=priority,
                    depends_on=depends_on or [],
                    relevant_files=relevant_files or [],
                    relevant_services=relevant_services or [],
                    agent_hint=agent_hint,
                )
            )
        )

    @app.tool()
    def claim_task(
        agent_id: str,
        hint_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        return _serialize_events(
            service.handle(ClaimTask(agent_id=agent_id, hint_filter=hint_filter))
        )

    @app.tool()
    def complete_task(
        task_id: str,
        summary: str,
        session_id: str | None = None,
        artifacts: list[str] | None = None,
        tokens: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        return _serialize_events(
            service.handle(
                CompleteTask(
                    task_id=task_id,
                    session_id=session_id,
                    summary=summary,
                    artifacts=artifacts or [],
                    tokens=_token_usage(tokens),
                )
            )
        )

    @app.tool()
    def fail_task(
        task_id: str,
        session_id: str,
        reason: str,
        retry: bool = False,
        tokens: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        return _serialize_events(
            service.handle(
                FailTask(
                    task_id=task_id,
                    session_id=session_id,
                    reason=reason,
                    retry=retry,
                    tokens=_token_usage(tokens),
                )
            )
        )

    @app.tool()
    def block_task(
        task_id: str,
        session_id: str,
        reason: str,
        tokens: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        return _serialize_events(
            service.handle(
                BlockTask(
                    task_id=task_id,
                    session_id=session_id,
                    reason=reason,
                    tokens=_token_usage(tokens),
                )
            )
        )

    @app.tool()
    def split_task(
        parent_id: str, subtasks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return _serialize_events(
            service.handle(
                SplitTask(
                    parent_id=parent_id,
                    subtasks=[_subtask_input(item) for item in subtasks],
                )
            )
        )

    @app.tool()
    def add_note(task_id: str, note: str) -> list[dict[str, Any]]:
        return _serialize_events(service.handle(AddNote(task_id=task_id, note=note)))

    @app.tool()
    def list_tasks(
        status: str | None = None,
        agent_hint: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            _serialize(task)
            for task in service.list_tasks(status=status, agent_hint=agent_hint)
        ]

    @app.tool()
    def health() -> dict[str, Any]:
        return _serialize(service.health_report())

    @app.tool()
    def stats() -> dict[str, Any]:
        return _serialize(service.queue_stats())

    @app.tool()
    def get_task(task_id: str) -> dict[str, Any]:
        return _serialize(service.get_task(task_id))

    @app.tool()
    def open_session(
        task_id: str,
        stage: str,
        agent_id: str,
        model_family: str | None = None,
        model_version: str | None = None,
        model_name: str | None = None,
        operating_mode: str | None = None,
        rule_set_version: str | None = None,
        instructions_fingerprint: str | None = None,
        session_ref: str | None = None,
        skills_used: list[str] | None = None,
        tool_calls_summary: dict[str, int] | None = None,
        tool_calls_summary_tokens: dict[str, int] | None = None,
        design_patterns: list[str] | None = None,
        decision_notes: str | None = None,
        theory_notes: str | None = None,
        notes: str | None = None,
    ) -> list[dict[str, Any]]:
        return _serialize_events(
            service.handle(
                OpenSession(
                    task_id=task_id,
                    stage=stage,
                    agent_id=agent_id,
                    model_name=model_name,
                    model_family=model_family,
                    model_version=model_version,
                    operating_mode=operating_mode,
                    rule_set_version=rule_set_version,
                    instructions_fingerprint=instructions_fingerprint,
                    session_ref=session_ref,
                    skills_used=skills_used or [],
                    tool_calls_summary=tool_calls_summary or {},
                    tool_calls_summary_tokens=_token_usage(tool_calls_summary_tokens),
                    design_patterns=design_patterns or [],
                    decision_notes=decision_notes,
                    theory_notes=theory_notes,
                    notes=notes,
                )
            )
        )

    @app.tool()
    def close_session(
        session_id: str,
        outcome: str,
        summary: str | None = None,
        tokens: dict[str, int] | None = None,
        rule_set_version: str | None = None,
        instructions_fingerprint: str | None = None,
        skills_used: list[str] | None = None,
        tool_calls_summary: dict[str, int] | None = None,
        tool_calls_summary_tokens: dict[str, int] | None = None,
        design_patterns: list[str] | None = None,
        decision_notes: str | None = None,
        theory_notes: str | None = None,
        notes: str | None = None,
        artifacts: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        return _serialize_events(
            service.handle(
                CloseSession(
                    session_id=session_id,
                    outcome=outcome,
                    summary=summary,
                    tokens=_token_usage(tokens),
                    rule_set_version=rule_set_version,
                    instructions_fingerprint=instructions_fingerprint,
                    skills_used=skills_used or [],
                    tool_calls_summary=tool_calls_summary or {},
                    tool_calls_summary_tokens=_token_usage(tool_calls_summary_tokens),
                    design_patterns=design_patterns or [],
                    decision_notes=decision_notes,
                    theory_notes=theory_notes,
                    notes=notes,
                    artifacts=artifacts or [],
                )
            )
        )

    @app.tool()
    def log_tokens(
        session_id: str | None = None,
        agent_id: str | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cache_read: int = 0,
        cache_write: int = 0,
        note: str | None = None,
        replace: bool = False,
    ) -> list[dict[str, Any]]:
        """Attribute token usage to a session. Pass either ``session_id``
        or ``agent_id`` (not both) — the latter resolves to the agent's
        currently-open session, which is what hooks should use.
        ``replace=True`` overwrites the totals instead of adding; idempotent
        across re-fires of a transcript-summing hook."""
        return _serialize_events(
            service.handle(
                LogTokens(
                    session_id=session_id,
                    agent_id=agent_id,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cache_read=cache_read,
                    cache_write=cache_write,
                    note=note,
                    replace=replace,
                )
            )
        )

    @app.tool()
    def log_tool_calls_summary(
        session_id: str,
        tool_calls_summary: dict[str, int],
        tokens: dict[str, int] | None = None,
        note: str | None = None,
    ) -> list[dict[str, Any]]:
        return _serialize_events(
            service.handle(
                LogToolCallsSummary(
                    session_id=session_id,
                    tool_calls_summary=tool_calls_summary,
                    tokens=_token_usage(tokens),
                    note=note,
                )
            )
        )

    @app.tool()
    def request_feature(
        title: str,
        kind: str,
        detail: str,
        task_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        model_name: str | None = None,
        notes: str | None = None,
    ) -> list[dict[str, Any]]:
        return _serialize_events(
            service.handle(
                RequestFeature(
                    title=title,
                    kind=kind,
                    detail=detail,
                    task_id=task_id,
                    session_id=session_id,
                    agent_id=agent_id,
                    model_name=model_name,
                    notes=notes,
                )
            )
        )

    @app.tool()
    def resolve_feature_request(
        feature_request_id: str,
        resolution: str,
        task_id: str | None = None,
        note: str | None = None,
    ) -> list[dict[str, Any]]:
        """Close a feature request. ``resolution`` is one of
        ``discarded`` (won't fix / not applicable),
        ``already_complete`` (already addressed elsewhere), or
        ``converted_to_task`` (work is now tracked as a task — pass
        the new task's id via ``task_id``)."""
        return _serialize_events(
            service.handle(
                ResolveFeatureRequest(
                    feature_request_id=feature_request_id,
                    resolution=resolution,
                    task_id=task_id,
                    note=note,
                )
            )
        )

    @app.tool()
    def sweep_stale_sessions(
        max_age_hours: int = 48,
    ) -> list[dict[str, Any]]:
        """Close any open session that started more than ``max_age_hours``
        ago, with outcome="abandoned". Drop-off recovery floor."""
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
        return _serialize_events(
            service.handle(SweepStaleSessions(cutoff_iso=cutoff.isoformat()))
        )

    @app.tool()
    def list_feature_requests(
        status: str | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            _serialize(feature_request)
            for feature_request in service.list_feature_requests(
                status=status, kind=kind
            )
        ]

    @app.tool()
    def list_open_sessions() -> list[dict[str, Any]]:
        """Open sessions joined to task title/status. Answers 'who's
        working on what right now'."""
        return [_serialize(view) for view in service.list_open_sessions()]

    @app.tool()
    def list_session_notes(
        task_id: str | None = None,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        """Sessions carrying decision_notes / theory_notes /
        design_patterns. Optional ``task_id`` and ISO-8601 ``since``
        filters."""
        return [
            _serialize(view)
            for view in service.list_session_notes(task_id=task_id, since=since)
        ]

    @app.tool()
    def agent_activity() -> list[dict[str, Any]]:
        """Per-agent breakdown: sessions opened/closed, tasks completed,
        token totals, tool counts."""
        return [_serialize(activity) for activity in service.agent_activity()]

    @app.tool()
    def tool_calls_canonical() -> dict[str, Any]:
        """Aggregate tool-call counts under canonical names, collapsing
        the codex/claude alias bifurcation. Returns ``counts`` and the
        ``aliases`` actually applied."""
        return _serialize(service.tool_calls_canonical())

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the queue MCP server.")
    parser.add_argument("--db", default="./queue.db", help="SQLite database path.")
    parser.add_argument(
        "--transport",
        choices=("http", "stdio"),
        default="http",
        help="MCP transport to use.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host.")
    parser.add_argument("--port", type=int, default=8483, help="HTTP bind port.")
    args = parser.parse_args()

    app = create_app(db_path=args.db)
    if args.transport == "stdio":
        app.run(transport="stdio")
        return
    app.run(transport="http", host=args.host, port=args.port)


def _serialize_events(events: list[Any]) -> list[dict[str, Any]]:
    return [_serialize(event) for event in events]


def _serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(cast(Any, value))
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


def _token_usage(tokens: dict[str, int] | None) -> TokenUsage | None:
    if tokens is None:
        return None
    return TokenUsage(
        tokens_in=tokens.get("tokens_in", 0),
        tokens_out=tokens.get("tokens_out", 0),
        tokens_cache_read=tokens.get("tokens_cache_read", 0),
        tokens_cache_write=tokens.get("tokens_cache_write", 0),
    )


def _subtask_input(value: dict[str, Any]) -> SubtaskInput:
    return SubtaskInput(
        title=value["title"],
        description=value.get("description"),
        priority=value.get("priority", 50),
        depends_on=value.get("depends_on", []),
        relevant_files=value.get("relevant_files", []),
        relevant_services=value.get("relevant_services", []),
        agent_hint=value.get("agent_hint"),
        notes=value.get("notes"),
    )


if __name__ == "__main__":
    main()
