from __future__ import annotations

import pytest

from domain.commands import (
    AddIdea,
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
from domain.events import (
    ClaimFailed,
    DependentsUnblocked,
    FeatureRequested,
    FeatureRequestResolved,
    SessionClosed,
    SessionOpened,
    StaleSessionsSwept,
    TaskClaimed,
    TaskCompleted,
    TaskRetried,
    TaskSplit,
)
from domain.models import TokenUsage
from domain.queue import QueueService
from tests.fixtures import FakeClock, InMemoryRepository


def make_service() -> QueueService:
    clock = FakeClock()
    repository = InMemoryRepository()
    return QueueService(repository=repository, now_factory=clock.now)


def add_scoped_task(
    service: QueueService,
    title: str,
    *,
    priority: int = 50,
    depends_on: list[str] | None = None,
    agent_hint: str | None = None,
) -> str:
    idea_event = service.handle(AddIdea(title=title))[0]
    task_id = idea_event.task.id
    service.handle(
        ScopeTask(
            task_id=task_id,
            description=f"{title} description",
            context=f"{title} context",
            priority=priority,
            depends_on=depends_on or [],
            agent_hint=agent_hint,
        )
    )
    return task_id


def test_claim_task_is_not_returned_twice():
    service = make_service()
    add_scoped_task(service, "first task")

    first_claim = service.handle(ClaimTask(agent_id="claude-code"))
    second_claim = service.handle(ClaimTask(agent_id="codex"))

    assert isinstance(first_claim[0], TaskClaimed)
    assert isinstance(second_claim[0], ClaimFailed)


def test_complete_task_promotes_newly_unblocked_dependents():
    service = make_service()
    parent_id = add_scoped_task(service, "parent")
    child_id = add_scoped_task(service, "child", depends_on=[parent_id])

    claim_event = service.handle(ClaimTask(agent_id="claude-code"))[0]
    result = service.handle(
        CompleteTask(
            task_id=parent_id,
            session_id=claim_event.session.id,
            summary="done",
        )
    )

    child = service.get_task(child_id).task

    assert child.status == "ready"
    assert any(
        isinstance(event, DependentsUnblocked) and child_id in event.task_ids
        for event in result
    )


def test_split_task_blocks_parent_until_all_children_are_done():
    service = make_service()
    parent_id = add_scoped_task(service, "parent")

    split_events = service.handle(
        SplitTask(
            parent_id=parent_id,
            subtasks=[
                SubtaskInput(title="child one"),
                SubtaskInput(title="child two"),
            ],
        )
    )

    assert isinstance(split_events[0], TaskSplit)
    assert len(split_events[0].children) == 2
    assert service.get_task(parent_id).task.status == "blocked"

    first_claim = service.handle(ClaimTask(agent_id="claude-code"))[0]
    service.handle(
        CompleteTask(
            task_id=first_claim.task.id,
            session_id=first_claim.session.id,
            summary="done",
        )
    )
    assert service.get_task(parent_id).task.status == "blocked"

    second_claim = service.handle(ClaimTask(agent_id="codex"))[0]
    service.handle(
        CompleteTask(
            task_id=second_claim.task.id,
            session_id=second_claim.session.id,
            summary="done",
        )
    )

    assert service.get_task(parent_id).task.status == "ready"


def test_fail_task_with_retry_returns_to_ready():
    service = make_service()
    task_id = add_scoped_task(service, "retry me")

    claim_event = service.handle(ClaimTask(agent_id="claude-code"))[0]
    result = service.handle(
        FailTask(
            task_id=task_id,
            session_id=claim_event.session.id,
            reason="temporary issue",
            retry=True,
        )
    )

    task = service.get_task(task_id).task

    assert task.status == "ready"
    assert any(isinstance(event, TaskRetried) for event in result)


def test_get_task_rolls_up_tokens_across_sessions():
    service = make_service()
    task_id = add_scoped_task(service, "token task")

    review_session = service.handle(
        OpenSession(task_id=task_id, stage="review", agent_id="claude-code")
    )[0].session
    service.handle(
        LogTokens(
            session_id=review_session.id,
            tokens_in=10,
            tokens_out=5,
            cache_read=2,
            cache_write=1,
        )
    )

    claim_event = service.handle(ClaimTask(agent_id="codex"))[0]
    service.handle(
        CompleteTask(
            task_id=task_id,
            session_id=claim_event.session.id,
            summary="done",
            tokens=TokenUsage(tokens_in=20, tokens_out=8, tokens_cache_read=3),
        )
    )

    detail = service.get_task(task_id)

    assert detail.token_rollup.tokens_in == 30
    assert detail.token_rollup.tokens_out == 13
    assert detail.token_rollup.tokens_cache_read == 5
    assert detail.token_rollup.tokens_cache_write == 1


def test_claim_task_respects_hint_filter():
    service = make_service()
    add_scoped_task(service, "wrong hint", priority=1, agent_hint="frontend")
    target_id = add_scoped_task(
        service, "right hint", priority=10, agent_hint="network"
    )

    claim_event = service.handle(
        ClaimTask(agent_id="claude-code", hint_filter="network")
    )[0]

    assert isinstance(claim_event, TaskClaimed)
    assert claim_event.task.id == target_id


def test_claim_task_picks_highest_priority():
    service = make_service()
    add_scoped_task(service, "low", priority=10)
    target_id = add_scoped_task(service, "high", priority=80)
    add_scoped_task(service, "medium", priority=50)

    claim_event = service.handle(ClaimTask(agent_id="claude-code"))[0]

    assert isinstance(claim_event, TaskClaimed)
    assert claim_event.task.id == target_id


def test_claim_task_priority_ties_break_by_creation_order():
    service = make_service()
    first_id = add_scoped_task(service, "first", priority=50)
    add_scoped_task(service, "second", priority=50)

    claim_event = service.handle(ClaimTask(agent_id="claude-code"))[0]

    assert isinstance(claim_event, TaskClaimed)
    assert claim_event.task.id == first_id


def test_claim_task_with_hint_filter_still_picks_highest_priority():
    service = make_service()
    add_scoped_task(service, "off-hint high", priority=90, agent_hint="design-agent")
    add_scoped_task(service, "on-hint low", priority=20, agent_hint="coding-agent")
    target_id = add_scoped_task(
        service, "on-hint high", priority=70, agent_hint="coding-agent"
    )

    claim_event = service.handle(
        ClaimTask(agent_id="claude-code", hint_filter="coding-agent")
    )[0]

    assert isinstance(claim_event, TaskClaimed)
    assert claim_event.task.id == target_id


def test_claim_task_hint_filter_excludes_unhinted_tasks():
    service = make_service()
    add_scoped_task(service, "no hint", priority=90)
    target_id = add_scoped_task(service, "hinted", priority=10, agent_hint="codex")

    claim_event = service.handle(
        ClaimTask(agent_id="claude-code", hint_filter="codex")
    )[0]

    assert isinstance(claim_event, TaskClaimed)
    assert claim_event.task.id == target_id


def test_health_report_reflects_basic_queue_state():
    service = make_service()
    task_id = add_scoped_task(service, "health task")
    service.handle(
        OpenSession(task_id=task_id, stage="execution", agent_id="claude-code")
    )

    report = service.health_report()

    assert report.ok is True
    assert report.schema_ready is True
    assert report.task_count == 1
    assert report.session_count == 1
    assert report.feature_request_count == 0
    assert report.checked_at


def test_queue_stats_aggregate_counts_and_tokens():
    service = make_service()
    task_id = add_scoped_task(service, "stats task", agent_hint="backend")
    blocked_id = add_scoped_task(service, "blocked task")
    service.handle(
        ScopeTask(
            task_id=blocked_id,
            description="blocked",
            context="waiting on dependency",
            priority=50,
            depends_on=["task_missing"],
        )
    )
    session = service.handle(
        OpenSession(task_id=task_id, stage="execution", agent_id="claude-code")
    )[0].session
    service.handle(
        LogTokens(
            session_id=session.id,
            tokens_in=7,
            tokens_out=3,
            cache_read=1,
            cache_write=2,
        )
    )
    service.handle(
        RequestFeature(
            title="Add stats view",
            kind="repetitive_work",
            detail="Need quick queue inspection.",
            task_id=task_id,
            session_id=session.id,
            agent_id="claude-code",
        )
    )

    stats = service.queue_stats()

    assert stats.task_count_total == 2
    assert stats.task_counts_by_status["ready"] == 1
    assert stats.task_counts_by_status["blocked"] == 1
    assert stats.session_count_total == 1
    assert stats.sessions_by_stage["execution"] == 1
    assert stats.open_session_count == 1
    assert stats.feature_request_count_total == 1
    assert stats.feature_requests_by_kind["repetitive_work"] == 1
    assert stats.token_totals.tokens_in == 7
    assert stats.token_totals.tokens_cache_write == 2


def test_log_tool_calls_summary_tracks_counts_and_separate_token_cost():
    service = make_service()
    task_id = add_scoped_task(service, "tool summary task")
    session = service.handle(
        OpenSession(task_id=task_id, stage="execution", agent_id="claude-code")
    )[0].session

    event = service.handle(
        LogToolCallsSummary(
            session_id=session.id,
            tool_calls_summary={"web.search": 2, "git": 1},
            tokens=TokenUsage(tokens_in=9, tokens_out=4, tokens_cache_read=1),
            note="Summarized the main tool usage for later analysis.",
        )
    )[0]

    updated_session = event.session
    stats = service.queue_stats()

    assert updated_session.tool_calls_summary == {"web.search": 2, "git": 1}
    assert updated_session.tool_calls_summary_tokens.tokens_in == 9
    assert updated_session.tool_calls_summary_tokens.tokens_out == 4
    assert "Summarized the main tool usage" in updated_session.notes
    assert stats.tool_calls_summary_totals["web.search"] == 2
    assert stats.tool_calls_summary_totals["git"] == 1
    assert stats.tool_calls_summary_token_totals.tokens_in == 9


def test_open_session_captures_practical_agent_metadata():
    service = make_service()
    task_id = add_scoped_task(service, "metadata task")

    event = service.handle(
        OpenSession(
            task_id=task_id,
            stage="scoping",
            agent_id="claude-code",
            model_name="gpt-5.5",
            operating_mode="default",
            rule_set_version="ruleset-2026-04-24",
            instructions_fingerprint="sha256:abc123",
            session_ref="conversation://123",
            skills_used=["openai-docs", "repo-audit"],
            design_patterns=["repository pattern", "import-first IaC"],
            decision_notes="Prefer audit before scaffolding to avoid creating a second structure.",
            theory_notes="Model the work as a dependency graph; stabilize the root before adding generators.",
            notes="Started after detecting drift in the queue spec.",
        )
    )[0]

    assert isinstance(event, SessionOpened)
    assert event.session.model_name == "gpt-5.5"
    assert event.session.operating_mode == "default"
    assert event.session.rule_set_version == "ruleset-2026-04-24"
    assert event.session.instructions_fingerprint == "sha256:abc123"
    assert event.session.session_ref == "conversation://123"
    assert event.session.skills_used == ["openai-docs", "repo-audit"]
    assert event.session.design_patterns == ["repository pattern", "import-first IaC"]
    assert "Prefer audit before scaffolding" in event.session.decision_notes
    assert "dependency graph" in event.session.theory_notes
    assert event.session.notes == "Started after detecting drift in the queue spec."
    assert event.session.started_at


def test_request_feature_records_blockers_and_repetition_signals():
    service = make_service()
    task_id = add_scoped_task(service, "feature request source")
    session = service.handle(
        OpenSession(
            task_id=task_id,
            stage="execution",
            agent_id="claude-code",
            model_name="gpt-5.5",
        )
    )[0].session

    event = service.handle(
        RequestFeature(
            title="Add branch bootstrap helper",
            kind="repetitive_work",
            detail="Agents keep repeating the same branch + PR setup steps.",
            task_id=task_id,
            session_id=session.id,
            agent_id="claude-code",
            model_name="gpt-5.5",
            notes="Should expose one command that prepares branch naming and PR template text.",
        )
    )[0]

    assert isinstance(event, FeatureRequested)
    assert event.feature_request.kind == "repetitive_work"
    assert event.feature_request.task_id == task_id
    assert event.feature_request.session_id == session.id
    assert event.feature_request.model_name == "gpt-5.5"


def _request_feature(service: QueueService, **overrides) -> str:
    defaults = dict(
        title="title",
        kind="guidance_gap",
        detail="detail",
    )
    defaults.update(overrides)
    return service.handle(RequestFeature(**defaults))[0].feature_request.id


def test_resolve_feature_request_discarded_marks_resolved_with_note():
    service = make_service()
    fr_id = _request_feature(service)

    event = service.handle(
        ResolveFeatureRequest(
            feature_request_id=fr_id,
            resolution="discarded",
            note="Not applicable after re-scoping.",
        )
    )[0]

    assert isinstance(event, FeatureRequestResolved)
    assert event.feature_request.status == "resolved"
    assert event.feature_request.resolution == "discarded"
    assert event.feature_request.resolution_task_id is None
    assert "Not applicable" in event.feature_request.notes


def test_resolve_feature_request_already_complete():
    service = make_service()
    fr_id = _request_feature(service)

    event = service.handle(
        ResolveFeatureRequest(
            feature_request_id=fr_id,
            resolution="already_complete",
        )
    )[0]

    assert event.feature_request.resolution == "already_complete"
    assert event.feature_request.resolution_task_id is None


def test_resolve_feature_request_converted_to_task_links_task():
    service = make_service()
    fr_id = _request_feature(service)
    new_task_id = add_scoped_task(service, "follow-up task")

    event = service.handle(
        ResolveFeatureRequest(
            feature_request_id=fr_id,
            resolution="converted_to_task",
            task_id=new_task_id,
            note="Tracked as the new task.",
        )
    )[0]

    assert event.feature_request.resolution == "converted_to_task"
    assert event.feature_request.resolution_task_id == new_task_id


def test_resolve_feature_request_rejects_unknown_resolution():
    service = make_service()
    fr_id = _request_feature(service)

    with pytest.raises(ValueError, match="Unknown resolution"):
        service.handle(
            ResolveFeatureRequest(
                feature_request_id=fr_id,
                resolution="closed",
            )
        )


def test_resolve_feature_request_requires_task_id_for_conversion():
    service = make_service()
    fr_id = _request_feature(service)

    with pytest.raises(ValueError, match="task_id is required"):
        service.handle(
            ResolveFeatureRequest(
                feature_request_id=fr_id,
                resolution="converted_to_task",
            )
        )


def test_resolve_feature_request_rejects_unknown_task_id():
    service = make_service()
    fr_id = _request_feature(service)

    with pytest.raises(ValueError, match="not found"):
        service.handle(
            ResolveFeatureRequest(
                feature_request_id=fr_id,
                resolution="converted_to_task",
                task_id="task_does_not_exist",
            )
        )


def test_resolve_feature_request_rejects_task_id_for_non_conversion():
    service = make_service()
    fr_id = _request_feature(service)
    other_task = add_scoped_task(service, "stray task")

    with pytest.raises(ValueError, match="only accepted"):
        service.handle(
            ResolveFeatureRequest(
                feature_request_id=fr_id,
                resolution="discarded",
                task_id=other_task,
            )
        )


def test_resolve_feature_request_rejects_double_resolution():
    service = make_service()
    fr_id = _request_feature(service)
    service.handle(
        ResolveFeatureRequest(
            feature_request_id=fr_id,
            resolution="discarded",
        )
    )

    with pytest.raises(ValueError, match="already resolved"):
        service.handle(
            ResolveFeatureRequest(
                feature_request_id=fr_id,
                resolution="already_complete",
            )
        )


def test_close_session_merges_skills_patterns_and_analysis_notes():
    service = make_service()
    task_id = add_scoped_task(service, "session close task")

    session = service.handle(
        OpenSession(
            task_id=task_id,
            stage="execution",
            agent_id="claude-code",
            model_name="gpt-5.5",
            operating_mode="plan",
            rule_set_version="ruleset-2026-04-24",
            instructions_fingerprint="sha256:before-close",
            skills_used=["skill-creator"],
            design_patterns=["repository pattern"],
            decision_notes="Start narrow and domain-first.",
            theory_notes="Prefer minimizing state-space before persistence.",
            notes="Initial pass.",
        )
    )[0].session

    closed = service.handle(
        CloseSession(
            session_id=session.id,
            outcome="completed",
            summary="Session done",
            rule_set_version="ruleset-2026-04-25",
            instructions_fingerprint="sha256:after-close",
            skills_used=["skill-creator", "openai-docs"],
            design_patterns=["repository pattern", "event sourcing"],
            decision_notes="Persistence can follow once the interface stops moving.",
            theory_notes="Delayed commitment reduces rework under changing constraints.",
            notes="Wrapped up after tests passed.",
        )
    )[0].session

    assert closed.rule_set_version == "ruleset-2026-04-25"
    assert closed.instructions_fingerprint == "sha256:after-close"
    assert closed.skills_used == ["skill-creator", "openai-docs"]
    assert closed.design_patterns == ["repository pattern", "event sourcing"]
    assert "Start narrow and domain-first." in closed.decision_notes
    assert "Persistence can follow" in closed.decision_notes
    assert "minimizing state-space" in closed.theory_notes
    assert "Delayed commitment" in closed.theory_notes


# ---------- session lifecycle resilience (task_xazdmw) ----------


def test_open_session_auto_closes_prior_open_session_for_same_agent():
    """Drop-off recovery: when the same agent opens a new session, any
    prior open session of theirs gets superseded automatically."""
    service = make_service()
    task_a = add_scoped_task(service, "task A")
    task_b = add_scoped_task(service, "task B")

    first_open = service.handle(
        OpenSession(task_id=task_a, stage="execution", agent_id="claude-code")
    )
    first_session = first_open[-1].session

    second_open = service.handle(
        OpenSession(task_id=task_b, stage="execution", agent_id="claude-code")
    )

    closed_events = [e for e in second_open if isinstance(e, SessionClosed)]
    assert len(closed_events) == 1
    assert closed_events[0].session.id == first_session.id
    assert closed_events[0].session.outcome == "superseded"


def test_open_session_does_not_close_prior_session_of_different_agent():
    service = make_service()
    task_a = add_scoped_task(service, "task A")
    task_b = add_scoped_task(service, "task B")

    service.handle(
        OpenSession(task_id=task_a, stage="execution", agent_id="claude-code")
    )
    second = service.handle(
        OpenSession(task_id=task_b, stage="execution", agent_id="codex")
    )

    assert any(isinstance(e, SessionOpened) for e in second)
    assert not any(isinstance(e, SessionClosed) for e in second)


def test_complete_task_with_explicit_session_id_validates_task_match():
    """Cross-task orphaning is the failure mode that produced PR #32's
    stale opens; refuse it loudly instead."""
    service = make_service()
    task_a = add_scoped_task(service, "task A")
    task_b = add_scoped_task(service, "task B")
    session_a = service.handle(
        OpenSession(task_id=task_a, stage="execution", agent_id="claude-code")
    )[-1].session

    with pytest.raises(ValueError, match="belongs to task"):
        service.handle(
            CompleteTask(
                task_id=task_b,
                session_id=session_a.id,
                summary="completing the wrong task",
            )
        )


def test_complete_task_without_session_id_closes_all_open_sessions_for_task():
    """Auto-close path: omitting session_id closes every open session for
    the task. Drop-off recovery from outside — no need to know the ids."""
    service = make_service()
    task_id = add_scoped_task(service, "shared task")
    first = service.handle(
        OpenSession(task_id=task_id, stage="execution", agent_id="claude-code")
    )[-1].session
    # The 'agent_y' open will not auto-close 'agent_x's session because they
    # have different agent_ids — the open_session per-agent recovery only
    # applies to same-agent reopens.
    second = service.handle(
        OpenSession(task_id=task_id, stage="execution", agent_id="codex")
    )[-1].session

    events = service.handle(CompleteTask(task_id=task_id, summary="all done"))

    completed = next(e for e in events if isinstance(e, TaskCompleted))
    closed_ids = {s.id for s in completed.sessions}
    assert closed_ids == {first.id, second.id}
    assert all(s.outcome == "completed" for s in completed.sessions)


def test_complete_task_without_session_id_succeeds_when_no_open_sessions():
    """A task can be marked done even if it has no open sessions (e.g.
    queue meta-tasks created and completed without session ceremony)."""
    service = make_service()
    task_id = add_scoped_task(service, "no-session task")

    events = service.handle(
        CompleteTask(task_id=task_id, summary="done without ceremony")
    )

    completed = next(e for e in events if isinstance(e, TaskCompleted))
    assert completed.task.status == "done"
    assert completed.sessions == []


def test_sweep_stale_sessions_closes_sessions_started_before_cutoff():
    service = make_service()
    task_id = add_scoped_task(service, "sweepable task")
    old = service.handle(
        OpenSession(task_id=task_id, stage="execution", agent_id="claude-code")
    )[-1].session

    # FakeClock issues monotonically increasing ISO timestamps. A cutoff
    # *after* `old.started_at` but *before* any subsequent session should
    # sweep `old` only.
    cutoff = "2026-04-24T12:00:99+00:00"

    events = service.handle(SweepStaleSessions(cutoff_iso=cutoff))

    swept = next(e for e in events if isinstance(e, StaleSessionsSwept))
    assert {s.id for s in swept.sessions} == {old.id}
    assert all(s.outcome == "abandoned" for s in swept.sessions)


def test_sweep_stale_sessions_skips_sessions_started_after_cutoff():
    service = make_service()
    task_id = add_scoped_task(service, "fresh task")
    service.handle(
        OpenSession(task_id=task_id, stage="execution", agent_id="claude-code")
    )

    cutoff = "2026-04-24T12:00:00+00:00"  # before any FakeClock tick

    events = service.handle(SweepStaleSessions(cutoff_iso=cutoff))

    swept = next(e for e in events if isinstance(e, StaleSessionsSwept))
    assert swept.sessions == []


# ---------- metadata visibility queries (task_txtk4g) ----------


def test_list_open_sessions_joins_task_title_and_status():
    service = make_service()
    task_id = add_scoped_task(service, "visible task")
    session = service.handle(
        OpenSession(task_id=task_id, stage="execution", agent_id="claude-code")
    )[-1].session
    # A second task with a closed session should not appear.
    other_task = add_scoped_task(service, "closed-session task")
    closed = service.handle(
        OpenSession(task_id=other_task, stage="execution", agent_id="codex")
    )[-1].session
    service.handle(
        CloseSession(session_id=closed.id, outcome="completed", summary="done")
    )

    views = service.list_open_sessions()

    assert len(views) == 1
    view = views[0]
    assert view.session_id == session.id
    assert view.agent_id == "claude-code"
    assert view.task_id == task_id
    assert view.task_title == "visible task"
    assert view.task_status == "ready"


def test_list_session_notes_filters_empty_and_sorts_recent_first():
    service = make_service()
    task_id = add_scoped_task(service, "notes task")
    # Session with no analysis content — must be filtered out. Each
    # subsequent same-agent open supersedes the prior; that's fine
    # here because list_session_notes ignores ended_at.
    service.handle(
        OpenSession(task_id=task_id, stage="execution", agent_id="claude-code")
    )
    early = service.handle(
        OpenSession(
            task_id=task_id,
            stage="scoping",
            agent_id="claude-code",
            decision_notes="picked the simple path",
        )
    )[-1].session
    later = service.handle(
        OpenSession(
            task_id=task_id,
            stage="execution",
            agent_id="claude-code",
            design_patterns=["repository pattern"],
            theory_notes="states converge under repeated application",
        )
    )[-1].session

    views = service.list_session_notes()

    assert [v.session_id for v in views] == [later.id, early.id]
    assert views[0].design_patterns == ["repository pattern"]
    assert views[1].decision_notes == "picked the simple path"


def test_list_session_notes_respects_task_and_since_filters():
    service = make_service()
    task_a = add_scoped_task(service, "task A")
    task_b = add_scoped_task(service, "task B")
    a_session = service.handle(
        OpenSession(
            task_id=task_a,
            stage="execution",
            agent_id="claude-code",
            decision_notes="A-side decision",
        )
    )[-1].session
    b_session = service.handle(
        OpenSession(
            task_id=task_b,
            stage="execution",
            agent_id="codex",
            decision_notes="B-side decision",
        )
    )[-1].session

    only_b = service.list_session_notes(task_id=task_b)
    assert [v.session_id for v in only_b] == [b_session.id]

    # Cutoff later than the A session's tick but before the B session's tick.
    since = "2026-04-24T12:00:99+00:00"
    only_recent = service.list_session_notes(since=since)
    assert all(v.session_id != a_session.id for v in only_recent)


def test_agent_activity_aggregates_per_agent_metrics():
    service = make_service()
    task_a = add_scoped_task(service, "agent A task")
    add_scoped_task(service, "agent A second task")
    add_scoped_task(service, "agent B task")

    a_first = service.handle(ClaimTask(agent_id="claude-code"))[0].session
    service.handle(
        LogToolCallsSummary(
            session_id=a_first.id,
            tool_calls_summary={"Bash": 4, "Read": 2},
        )
    )
    service.handle(
        CompleteTask(
            task_id=task_a,
            session_id=a_first.id,
            summary="A done",
            tokens=TokenUsage(tokens_in=100, tokens_out=50),
        )
    )
    a_second = service.handle(ClaimTask(agent_id="claude-code"))[0].session
    service.handle(
        LogToolCallsSummary(
            session_id=a_second.id,
            tool_calls_summary={"Bash": 1},
        )
    )

    b_session = service.handle(ClaimTask(agent_id="codex"))[0].session
    service.handle(
        FailTask(
            task_id=b_session.task_id,
            session_id=b_session.id,
            reason="ran out of time",
        )
    )

    activities = {a.agent_id: a for a in service.agent_activity()}

    assert set(activities) == {"claude-code", "codex"}
    a = activities["claude-code"]
    assert a.session_count == 2
    assert a.open_session_count == 1
    assert a.sessions_by_outcome.get("completed") == 1
    assert a.sessions_by_outcome.get("in_progress") == 1
    assert a.distinct_tasks == 2
    assert a.tasks_completed == 1
    assert a.token_totals.tokens_in == 100
    assert a.tool_calls == {"bash": 5, "read": 2}

    b = activities["codex"]
    assert b.session_count == 1
    assert b.open_session_count == 0
    assert b.sessions_by_outcome == {"failed": 1}
    assert b.tasks_completed == 0
    assert b.tool_calls == {}


def test_log_tool_calls_summary_canonicalizes_at_write_time():
    """Aliased names get folded onto canonical keys before they hit the
    session row. Unknown names pass through. The canonical view then has
    nothing to alias because the data is already canonical at rest."""
    service = make_service()
    task_id = add_scoped_task(service, "canonicalize me")
    session = service.handle(
        OpenSession(task_id=task_id, stage="execution", agent_id="codex")
    )[-1].session
    event = service.handle(
        LogToolCallsSummary(
            session_id=session.id,
            tool_calls_summary={
                "Bash": 3,
                "exec_command": 5,
                "queue_health": 1,
                "health": 2,
                "novel_tool": 7,
            },
        )
    )[0]

    assert event.session.tool_calls_summary == {
        "bash": 8,
        "queue_health": 3,
        "novel_tool": 7,
    }

    canonical = service.tool_calls_canonical()
    assert canonical.counts["bash"] == 8
    assert canonical.counts["queue_health"] == 3
    assert canonical.counts["novel_tool"] == 7
    assert canonical.aliases == {}
    assert list(canonical.counts) == ["bash", "novel_tool", "queue_health"]


def test_tool_calls_canonical_collapses_legacy_pre_canonical_rows():
    """Sessions that pre-date write-time canonicalization can still carry
    aliased keys at rest. The read-time view must keep collapsing them."""
    from domain.models import Session

    service = make_service()
    task_id = add_scoped_task(service, "legacy data")
    legacy_session = Session(
        id="session_legacy",
        task_id=task_id,
        stage="execution",
        agent_id="codex",
        tool_calls_summary={"Bash": 3, "exec_command": 5, "novel_tool": 2},
        started_at="2026-04-20T00:00:00+00:00",
    )
    service.repository.add_session(legacy_session)

    canonical = service.tool_calls_canonical()

    assert canonical.counts["bash"] == 8
    assert canonical.counts["novel_tool"] == 2
    assert canonical.aliases == {"Bash": "bash", "exec_command": "bash"}


# ---------- agent / model identity validation (task_0khzhw) ----------


def test_open_session_persists_validated_family_version_and_derives_name():
    service = make_service()
    task_id = add_scoped_task(service, "validated session")

    event = service.handle(
        OpenSession(
            task_id=task_id,
            stage="execution",
            agent_id="claude-code",
            model_family="claude-opus",
            model_version="4-7",
        )
    )[-1]

    assert event.session.agent_id == "claude-code"
    assert event.session.model_family == "claude-opus"
    assert event.session.model_version == "4-7"
    assert event.session.model_name == "claude-opus-4-7"


def test_open_session_rejects_unknown_agent_id():
    service = make_service()
    task_id = add_scoped_task(service, "rejection task")

    with pytest.raises(ValueError, match="Unknown agent_id"):
        service.handle(
            OpenSession(task_id=task_id, stage="execution", agent_id="bogus-cli")
        )


def test_open_session_rejects_family_from_wrong_provider():
    service = make_service()
    task_id = add_scoped_task(service, "wrong-provider task")

    with pytest.raises(ValueError, match="not valid for agent"):
        service.handle(
            OpenSession(
                task_id=task_id,
                stage="execution",
                agent_id="claude-code",
                model_family="gpt",
                model_version="5.5",
            )
        )


def test_claim_task_rejects_unknown_agent_id():
    service = make_service()
    add_scoped_task(service, "claimable")

    with pytest.raises(ValueError, match="Unknown agent_id"):
        service.handle(ClaimTask(agent_id="agent_zzz"))


# ---------- log_tokens by agent + replace mode (task_s7ojxg) ----------


def test_log_tokens_by_agent_id_resolves_to_open_session():
    service = make_service()
    task_id = add_scoped_task(service, "tokens-by-agent")
    session = service.handle(
        OpenSession(task_id=task_id, stage="execution", agent_id="claude-code")
    )[-1].session

    service.handle(
        LogTokens(agent_id="claude-code", tokens_in=12, tokens_out=4, cache_read=2)
    )

    refreshed = service.repository.get_session(session.id)
    assert refreshed.tokens_in == 12
    assert refreshed.tokens_out == 4
    assert refreshed.tokens_cache_read == 2


def test_log_tokens_by_agent_id_errors_when_no_open_session():
    service = make_service()

    with pytest.raises(ValueError, match="No open session"):
        service.handle(LogTokens(agent_id="claude-code", tokens_in=1))


def test_log_tokens_rejects_both_session_id_and_agent_id():
    service = make_service()
    task_id = add_scoped_task(service, "exclusive selectors")
    session = service.handle(
        OpenSession(task_id=task_id, stage="execution", agent_id="claude-code")
    )[-1].session

    with pytest.raises(ValueError, match="exactly one"):
        service.handle(
            LogTokens(session_id=session.id, agent_id="claude-code", tokens_in=1)
        )


def test_log_tokens_rejects_neither_session_id_nor_agent_id():
    service = make_service()

    with pytest.raises(ValueError, match="exactly one"):
        service.handle(LogTokens(tokens_in=1))


def test_log_tokens_replace_mode_overwrites_running_totals():
    """Hooks that re-read a full transcript on each fire should be safe to
    re-run without double-counting."""
    service = make_service()
    task_id = add_scoped_task(service, "replace mode")
    session = service.handle(
        OpenSession(task_id=task_id, stage="execution", agent_id="claude-code")
    )[-1].session

    service.handle(LogTokens(session_id=session.id, tokens_in=10, tokens_out=5))
    service.handle(
        LogTokens(
            session_id=session.id,
            tokens_in=30,
            tokens_out=12,
            cache_read=4,
            replace=True,
        )
    )
    service.handle(
        LogTokens(
            session_id=session.id,
            tokens_in=30,
            tokens_out=12,
            cache_read=4,
            replace=True,
        )
    )

    refreshed = service.repository.get_session(session.id)
    assert refreshed.tokens_in == 30
    assert refreshed.tokens_out == 12
    assert refreshed.tokens_cache_read == 4


def test_open_session_falls_back_to_caller_model_name_when_no_family():
    """Back-compat: callers that haven't migrated to family+version yet
    can still pass a raw model_name; agent_id is still validated."""
    service = make_service()
    task_id = add_scoped_task(service, "legacy caller")

    event = service.handle(
        OpenSession(
            task_id=task_id,
            stage="execution",
            agent_id="codex",
            model_name="gpt-5.5",
        )
    )[-1]

    assert event.session.model_name == "gpt-5.5"
    assert event.session.model_family is None
    assert event.session.model_version is None
