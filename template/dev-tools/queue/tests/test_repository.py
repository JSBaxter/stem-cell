from __future__ import annotations

import sqlite3

from domain.models import FeatureRequest, Session, Task, TaskEvent, TokenUsage
from infra.repository import SQLiteRepository


def make_repository() -> SQLiteRepository:
    connection = sqlite3.connect(":memory:")
    repository = SQLiteRepository(connection)
    repository.init_schema()
    return repository


def test_sqlite_repository_round_trips_all_record_types():
    repository = make_repository()

    task = Task(
        id="task_123",
        title="Persist task",
        description="Ensure sqlite keeps structured fields intact.",
        status="ready",
        priority=10,
        depends_on=["task_dep"],
        relevant_files=["README.md"],
        relevant_services=["queue"],
        agent_hint="backend",
        notes="Task note",
        created_at="2026-04-24T12:00:01+00:00",
        updated_at="2026-04-24T12:00:02+00:00",
    )
    repository.add_task(task)

    session = Session(
        id="session_123",
        task_id=task.id,
        stage="execution",
        agent_id="claude-code",
        model_name="gpt-5.5",
        operating_mode="default",
        rule_set_version="ruleset-2026-04-24",
        instructions_fingerprint="sha256:sqlite-test",
        session_ref="conversation://abc",
        skills_used=["openai-docs", "repo-audit"],
        design_patterns=["repository pattern"],
        decision_notes="Start with persistence after the domain stabilizes.",
        theory_notes="Prefer normalized state transitions before exposing an API.",
        tokens_in=12,
        tokens_out=6,
        tokens_cache_read=2,
        tokens_cache_write=1,
        outcome="in_progress",
        summary="Working",
        notes="Session note",
        artifacts=["dev-tools/queue/infra/repository.py"],
        started_at="2026-04-24T12:00:03+00:00",
        ended_at=None,
    )
    repository.add_session(session)

    stored_event = repository.add_task_event(
        TaskEvent(
            task_id=task.id,
            from_status="idea",
            to_status="ready",
            actor="claude-code",
            note="Scoped successfully.",
            created_at="2026-04-24T12:00:04+00:00",
        )
    )

    feature_request = FeatureRequest(
        id="fr_123",
        title="Add queue dashboard",
        kind="guidance_gap",
        detail="Need a higher-level view of queue state during long sessions.",
        task_id=task.id,
        session_id=session.id,
        agent_id="claude-code",
        model_name="gpt-5.5",
        notes="Could become a later MCP or local web view.",
        created_at="2026-04-24T12:00:05+00:00",
        updated_at="2026-04-24T12:00:05+00:00",
    )
    repository.add_feature_request(feature_request)

    stored_task = repository.get_task(task.id)
    stored_session = repository.get_session(session.id)
    stored_events = repository.list_task_events(task.id)
    stored_feature_request = repository.get_feature_request(feature_request.id)

    assert stored_task == task
    assert stored_session == session
    assert stored_event.id is not None
    assert stored_events[0].note == "Scoped successfully."
    assert stored_feature_request == feature_request


def test_sqlite_repository_round_trips_feature_request_resolution():
    repository = make_repository()
    task = Task(
        id="task_resolve",
        title="Convert FR target",
        status="ready",
        created_at="2026-04-27T12:00:00+00:00",
        updated_at="2026-04-27T12:00:00+00:00",
    )
    repository.add_task(task)
    feature_request = FeatureRequest(
        id="fr_resolve",
        title="Become a task",
        kind="repetitive_work",
        detail="repeated steps",
        created_at="2026-04-27T12:00:01+00:00",
        updated_at="2026-04-27T12:00:01+00:00",
    )
    repository.add_feature_request(feature_request)

    resolved = FeatureRequest(
        id=feature_request.id,
        title=feature_request.title,
        kind=feature_request.kind,
        detail=feature_request.detail,
        status="resolved",
        resolution="converted_to_task",
        resolution_task_id=task.id,
        notes="Tracked as task_resolve.",
        created_at=feature_request.created_at,
        updated_at="2026-04-27T12:00:02+00:00",
    )
    repository.update_feature_request(resolved)

    assert repository.get_feature_request(feature_request.id) == resolved


def test_sqlite_repository_reports_health_and_stats():
    repository = make_repository()

    task = Task(
        id="task_stats",
        title="Stats task",
        status="ready",
        created_at="2026-04-24T12:00:01+00:00",
        updated_at="2026-04-24T12:00:01+00:00",
    )
    repository.add_task(task)

    session = Session(
        id="session_stats",
        task_id=task.id,
        stage="execution",
        agent_id="claude-code",
        tool_calls_summary={"rg": 3},
        tool_calls_summary_tokens=TokenUsage(tokens_in=5, tokens_out=2),
        tokens_in=11,
        tokens_out=4,
        started_at="2026-04-24T12:00:02+00:00",
    )
    repository.add_session(session)

    feature_request = FeatureRequest(
        id="fr_stats",
        title="Add health tool",
        kind="guidance_gap",
        detail="Need a lightweight readiness check.",
        task_id=task.id,
        session_id=session.id,
        created_at="2026-04-24T12:00:03+00:00",
        updated_at="2026-04-24T12:00:03+00:00",
    )
    repository.add_feature_request(feature_request)

    health = repository.health_report("2026-04-24T12:00:04+00:00")
    stats = repository.queue_stats()

    assert health.ok is True
    assert health.schema_ready is True
    assert health.task_count == 1
    assert health.session_count == 1
    assert health.feature_request_count == 1
    assert stats.task_count_total == 1
    assert stats.task_counts_by_status["ready"] == 1
    assert stats.sessions_by_stage["execution"] == 1
    assert stats.feature_requests_by_kind["guidance_gap"] == 1
    assert stats.token_totals.tokens_in == 11
    assert stats.tool_calls_summary_totals["rg"] == 3
    assert stats.tool_calls_summary_token_totals.tokens_in == 5
