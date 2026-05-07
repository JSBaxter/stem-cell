from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import Protocol

from .commands import (
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
    SweepStaleSessions,
)
from .events import (
    ClaimFailed,
    DependentsUnblocked,
    FeatureRequested,
    FeatureRequestResolved,
    IdeaAdded,
    SessionClosed,
    SessionOpened,
    StaleSessionsSwept,
    TaskBlocked,
    TaskClaimed,
    TaskCompleted,
    TaskFailed,
    TaskRetried,
    TaskScoped,
    TaskSplit,
    ToolCallsSummaryLogged,
    TokensLogged,
)
from .models import (
    AgentActivity,
    CanonicalToolCalls,
    FeatureRequest,
    HealthReport,
    OpenSessionView,
    QueueStats,
    Session,
    SessionNotesView,
    Task,
    TaskDetail,
    TaskEvent,
    TokenUsage,
)
from .providers import normalize_agent


# Maps the bifurcated tool names that surface in `tool_calls_summary`
# (codex `exec_command` vs claude `Bash`, codex `queue_*` vs claude bare
# names) to a single canonical key. Pass-through for anything not listed:
# the canonical view shouldn't lose data, only deduplicate the aliases
# the project actually sees. Applied at write-time so tool_calls_summary
# is canonical at rest; the read-time `tool_calls_canonical` view stays
# capable of collapsing any legacy rows that predate this.
_TOOL_NAME_ALIASES: dict[str, str] = {
    # built-in agent tools
    "Bash": "bash",
    "exec_command": "bash",
    "Edit": "edit",
    "edit_file": "edit",
    "apply_patch": "edit",
    "Read": "read",
    "view_file": "read",
    "read_file": "read",
    "Write": "write",
    "create_file": "write",
    "Grep": "grep",
    "ripgrep": "grep",
    "Glob": "glob",
    # queue MCP tools — claude bare names + codex queue_ prefix
    "health": "queue_health",
    "queue_health": "queue_health",
    "stats": "queue_stats",
    "queue_stats": "queue_stats",
    "list_tasks": "queue_list_tasks",
    "queue_list_tasks": "queue_list_tasks",
    "get_task": "queue_get_task",
    "queue_get_task": "queue_get_task",
    "open_session": "queue_open_session",
    "queue_open_session": "queue_open_session",
    "close_session": "queue_close_session",
    "queue_close_session": "queue_close_session",
    "complete_task": "queue_complete_task",
    "queue_complete_task": "queue_complete_task",
    "claim_task": "queue_claim_task",
    "queue_claim_task": "queue_claim_task",
    "add_note": "queue_add_note",
    "queue_add_note": "queue_add_note",
}


def _canonicalize_tool_counts(
    counts: dict[str, int],
) -> tuple[dict[str, int], dict[str, str]]:
    """Collapse aliased tool names onto their canonical key.

    Returns the canonicalized counts and the alias map actually used (raw
    name → canonical) — empty when the input was already canonical.
    Idempotent: re-running on canonical input is a no-op.
    """
    canonical: dict[str, int] = {}
    aliases_used: dict[str, str] = {}
    for raw_name, count in counts.items():
        target = _TOOL_NAME_ALIASES.get(raw_name, raw_name)
        canonical[target] = canonical.get(target, 0) + count
        if target != raw_name:
            aliases_used[raw_name] = target
    return canonical, aliases_used


class QueueRepository(Protocol):
    def add_task(self, task: Task) -> None: ...
    def update_task(self, task: Task) -> None: ...
    def get_task(self, task_id: str) -> Task | None: ...
    def list_tasks(self, status: str | None = None) -> list[Task]: ...
    def add_session(self, session: Session) -> None: ...
    def update_session(self, session: Session) -> None: ...
    def get_session(self, session_id: str) -> Session | None: ...
    def list_sessions(self, task_id: str | None = None) -> list[Session]: ...
    def list_open_sessions(
        self, task_id: str | None = None, agent_id: str | None = None
    ) -> list[Session]: ...
    def add_task_event(self, event: TaskEvent) -> TaskEvent: ...
    def list_task_events(self, task_id: str) -> list[TaskEvent]: ...
    def add_feature_request(self, feature_request: FeatureRequest) -> None: ...
    def update_feature_request(self, feature_request: FeatureRequest) -> None: ...
    def get_feature_request(self, feature_request_id: str) -> FeatureRequest | None: ...
    def list_feature_requests(
        self, status: str | None = None
    ) -> list[FeatureRequest]: ...
    def health_report(self, checked_at: str) -> HealthReport: ...
    def queue_stats(self) -> QueueStats: ...


class QueueService:
    def __init__(self, repository: QueueRepository, now_factory=None) -> None:
        self.repository = repository
        self.now_factory = now_factory or self._now

    def handle(self, command):
        if isinstance(command, AddIdea):
            return self._handle_add_idea(command)
        if isinstance(command, ScopeTask):
            return self._handle_scope_task(command)
        if isinstance(command, ClaimTask):
            return self._handle_claim_task(command)
        if isinstance(command, CompleteTask):
            return self._handle_complete_task(command)
        if isinstance(command, FailTask):
            return self._handle_fail_task(command)
        if isinstance(command, BlockTask):
            return self._handle_block_task(command)
        if isinstance(command, SplitTask):
            return self._handle_split_task(command)
        if isinstance(command, AddNote):
            return self._handle_add_note(command)
        if isinstance(command, OpenSession):
            return self._handle_open_session(command)
        if isinstance(command, CloseSession):
            return self._handle_close_session(command)
        if isinstance(command, LogTokens):
            return self._handle_log_tokens(command)
        if isinstance(command, LogToolCallsSummary):
            return self._handle_log_tool_calls_summary(command)
        if isinstance(command, RequestFeature):
            return self._handle_request_feature(command)
        if isinstance(command, ResolveFeatureRequest):
            return self._handle_resolve_feature_request(command)
        if isinstance(command, SweepStaleSessions):
            return self._handle_sweep_stale_sessions(command)
        raise TypeError(f"Unsupported command: {type(command)!r}")

    def get_task(self, task_id: str) -> TaskDetail:
        task = self._require_task(task_id)
        sessions = self.repository.list_sessions(task_id=task_id)
        token_rollup = TokenUsage()
        for session in sessions:
            token_rollup = token_rollup + session.token_usage()
        events = self.repository.list_task_events(task_id)
        return TaskDetail(
            task=task,
            sessions=sessions,
            token_rollup=token_rollup,
            events=events,
        )

    def list_tasks(
        self, status: str | None = None, agent_hint: str | None = None
    ) -> list[Task]:
        tasks = self.repository.list_tasks(status=status)
        if agent_hint is not None:
            tasks = [task for task in tasks if task.agent_hint == agent_hint]
        return tasks

    def list_feature_requests(
        self, status: str | None = None, kind: str | None = None
    ) -> list[FeatureRequest]:
        feature_requests = self.repository.list_feature_requests(status=status)
        if kind is not None:
            feature_requests = [
                feature_request
                for feature_request in feature_requests
                if feature_request.kind == kind
            ]
        return feature_requests

    def health_report(self) -> HealthReport:
        return self.repository.health_report(checked_at=self.now_factory())

    def queue_stats(self) -> QueueStats:
        return self.repository.queue_stats()

    def list_open_sessions(self) -> list[OpenSessionView]:
        """Open sessions joined to their owning task. Answers
        'who's working on what right now'."""
        sessions = self.repository.list_open_sessions()
        views: list[OpenSessionView] = []
        for session in sessions:
            task = self.repository.get_task(session.task_id)
            if task is None:
                continue
            views.append(
                OpenSessionView(
                    session_id=session.id,
                    agent_id=session.agent_id,
                    stage=session.stage,
                    started_at=session.started_at,
                    task_id=task.id,
                    task_title=task.title,
                    task_status=task.status,
                )
            )
        return views

    def list_session_notes(
        self,
        task_id: str | None = None,
        since: str | None = None,
    ) -> list[SessionNotesView]:
        """Sessions whose decision_notes / theory_notes / design_patterns
        carry content. Answers 'what decisions has the project made
        recently'. Sorted most-recent-first."""
        sessions = self.repository.list_sessions(task_id=task_id)
        views: list[SessionNotesView] = []
        for session in sessions:
            if since is not None and session.started_at < since:
                continue
            if not (
                session.decision_notes
                or session.theory_notes
                or session.design_patterns
            ):
                continue
            views.append(
                SessionNotesView(
                    session_id=session.id,
                    task_id=session.task_id,
                    agent_id=session.agent_id,
                    started_at=session.started_at,
                    ended_at=session.ended_at,
                    decision_notes=session.decision_notes,
                    theory_notes=session.theory_notes,
                    design_patterns=list(session.design_patterns),
                    summary=session.summary,
                )
            )
        views.sort(key=lambda v: v.started_at, reverse=True)
        return views

    def agent_activity(self) -> list[AgentActivity]:
        """Per-agent breakdown of sessions, tokens, and tool calls.
        Answers 'where is each agent's effort going'. Sorted by agent_id."""
        sessions = self.repository.list_sessions()
        by_agent: dict[str, list[Session]] = {}
        for session in sessions:
            by_agent.setdefault(session.agent_id, []).append(session)

        activities: list[AgentActivity] = []
        for agent_id in sorted(by_agent):
            agent_sessions = by_agent[agent_id]
            outcomes: dict[str, int] = {}
            tool_calls: dict[str, int] = {}
            tokens = TokenUsage()
            distinct_tasks: set[str] = set()
            completed_tasks: set[str] = set()
            open_count = 0
            for session in agent_sessions:
                outcome = session.outcome or "unknown"
                outcomes[outcome] = outcomes.get(outcome, 0) + 1
                tokens = tokens + session.token_usage()
                distinct_tasks.add(session.task_id)
                if outcome == "completed":
                    completed_tasks.add(session.task_id)
                if session.ended_at is None:
                    open_count += 1
                for name, count in session.tool_calls_summary.items():
                    tool_calls[name] = tool_calls.get(name, 0) + count
            activities.append(
                AgentActivity(
                    agent_id=agent_id,
                    session_count=len(agent_sessions),
                    open_session_count=open_count,
                    sessions_by_outcome=outcomes,
                    distinct_tasks=len(distinct_tasks),
                    tasks_completed=len(completed_tasks),
                    token_totals=tokens,
                    tool_calls=tool_calls,
                )
            )
        return activities

    def tool_calls_canonical(self) -> CanonicalToolCalls:
        """Aggregate tool-call counts under canonical names. Answers
        'what does the project do most' without the codex/claude name
        bifurcation showing as duplicate keys.

        New rows are canonicalized at write-time, so ``aliases`` is only
        non-empty when historical rows still carry pre-canonical names.
        """
        raw_totals = self.repository.queue_stats().tool_calls_summary_totals
        counts, aliases_used = _canonicalize_tool_counts(raw_totals)
        ordered_counts = dict(
            sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        )
        return CanonicalToolCalls(counts=ordered_counts, aliases=aliases_used)

    def _handle_add_idea(self, command: AddIdea):
        now = self.now_factory()
        task = Task(
            id=self._new_id("task"),
            title=command.title,
            notes=command.notes,
            status="idea",
            created_at=now,
            updated_at=now,
        )
        self.repository.add_task(task)
        self._record_transition(task, None, task.status, "system", command.notes)
        return [IdeaAdded(task)]

    def _handle_scope_task(self, command: ScopeTask):
        task = self._require_task(command.task_id)
        new_status = (
            "ready" if self._dependencies_satisfied(command.depends_on) else "blocked"
        )
        updated = replace(
            task,
            description=command.description,
            status=new_status,
            priority=command.priority,
            depends_on=list(command.depends_on),
            relevant_files=list(command.relevant_files),
            relevant_services=list(command.relevant_services),
            agent_hint=command.agent_hint,
            notes=self._append_note(task.notes, command.context),
            updated_at=self.now_factory(),
        )
        self.repository.update_task(updated)
        self._record_transition(
            updated,
            task.status,
            updated.status,
            "system",
            command.context,
        )
        return [TaskScoped(updated)]

    def _handle_claim_task(self, command: ClaimTask):
        identity = normalize_agent(command.agent_id)

        task = self._next_task(command.hint_filter)
        if task is None:
            return [ClaimFailed("No claimable task matched the filter.")]

        now = self.now_factory()
        claimed = replace(task, status="in_progress", updated_at=now)
        session = Session(
            id=self._new_id("session"),
            task_id=task.id,
            stage="execution",
            agent_id=identity.agent_id,
            outcome="in_progress",
            started_at=now,
        )
        self.repository.update_task(claimed)
        self.repository.add_session(session)
        self._record_transition(claimed, task.status, claimed.status, identity.agent_id)
        return [TaskClaimed(claimed, session)]

    def _handle_complete_task(self, command: CompleteTask):
        task = self._require_task(command.task_id)
        sessions = self._close_sessions_for_completion(
            task_id=command.task_id,
            session_id=command.session_id,
            summary=command.summary,
            tokens=command.tokens,
            artifacts=command.artifacts,
        )
        actor = sessions[-1].agent_id if sessions else "system"
        updated = replace(task, status="done", updated_at=self.now_factory())
        self.repository.update_task(updated)
        self._record_transition(updated, task.status, updated.status, actor)

        events: list[TaskCompleted | DependentsUnblocked] = [
            TaskCompleted(updated, sessions)
        ]
        unblocked = self._promote_unblocked_tasks(updated.id)
        if unblocked:
            events.append(DependentsUnblocked(unblocked))
        return events

    def _handle_fail_task(self, command: FailTask):
        task = self._require_task(command.task_id)
        session = self._close_task_session(
            command.session_id,
            outcome="failed",
            summary=command.reason,
            tokens=command.tokens,
        )
        next_status = "ready" if command.retry else "failed"
        updated = replace(task, status=next_status, updated_at=self.now_factory())
        self.repository.update_task(updated)
        self._record_transition(
            updated,
            task.status,
            updated.status,
            session.agent_id,
            command.reason,
        )
        events: list[TaskFailed | TaskRetried] = [TaskFailed(updated, session)]
        if command.retry:
            events.append(TaskRetried(updated))
        return events

    def _handle_block_task(self, command: BlockTask):
        task = self._require_task(command.task_id)
        session = self._close_task_session(
            command.session_id,
            outcome="handed_off",
            summary=command.reason,
            tokens=command.tokens,
        )
        updated = replace(task, status="blocked", updated_at=self.now_factory())
        self.repository.update_task(updated)
        self._record_transition(
            updated,
            task.status,
            updated.status,
            session.agent_id,
            command.reason,
        )
        return [TaskBlocked(updated, session)]

    def _handle_split_task(self, command: SplitTask):
        parent = self._require_task(command.parent_id)
        now = self.now_factory()
        children: list[Task] = []
        for subtask in command.subtasks:
            child = Task(
                id=self._new_id("task"),
                title=subtask.title,
                description=subtask.description,
                status=(
                    "ready"
                    if self._dependencies_satisfied(subtask.depends_on)
                    else "blocked"
                ),
                priority=subtask.priority,
                parent_id=parent.id,
                depends_on=list(subtask.depends_on),
                relevant_files=list(subtask.relevant_files),
                relevant_services=list(subtask.relevant_services),
                agent_hint=subtask.agent_hint,
                notes=subtask.notes,
                created_at=now,
                updated_at=now,
            )
            self.repository.add_task(child)
            self._record_transition(child, None, child.status, "system")
            children.append(child)

        blocked_parent = replace(parent, status="blocked", updated_at=now)
        self.repository.update_task(blocked_parent)
        self._record_transition(
            blocked_parent, parent.status, blocked_parent.status, "system"
        )
        return [TaskSplit(blocked_parent, children)]

    def _handle_add_note(self, command: AddNote):
        task = self._require_task(command.task_id)
        updated = replace(
            task,
            notes=self._append_note(task.notes, command.note),
            updated_at=self.now_factory(),
        )
        self.repository.update_task(updated)
        return []

    def _handle_open_session(self, command: OpenSession):
        self._require_task(command.task_id)
        identity = normalize_agent(
            command.agent_id,
            command.model_family,
            command.model_version,
        )

        # Drop-off recovery: if this agent has any prior open session,
        # supersede it. Eliminates the staleness pattern that produced
        # PR #32's sweep — the same agent reopening means the previous
        # session is, by definition, abandoned.
        prior_open = self.repository.list_open_sessions(agent_id=identity.agent_id)
        superseded: list[Session] = []
        for prior in prior_open:
            closed = self._supersede_session(
                prior,
                f"Auto-closed by open_session: agent {identity.agent_id} "
                f"opened a new session against task {command.task_id}.",
            )
            superseded.append(closed)

        canonical_summary, _ = _canonicalize_tool_counts(
            dict(command.tool_calls_summary)
        )
        session = Session(
            id=self._new_id("session"),
            task_id=command.task_id,
            stage=command.stage,
            agent_id=identity.agent_id,
            # Prefer the validated slug from family+version; fall back to
            # whatever model_name the legacy caller supplied (unvalidated).
            model_name=identity.model_name or command.model_name,
            model_family=identity.model_family,
            model_version=identity.model_version,
            operating_mode=command.operating_mode,
            rule_set_version=command.rule_set_version,
            instructions_fingerprint=command.instructions_fingerprint,
            session_ref=command.session_ref,
            skills_used=list(command.skills_used),
            tool_calls_summary=canonical_summary,
            tool_calls_summary_tokens=command.tool_calls_summary_tokens or TokenUsage(),
            design_patterns=list(command.design_patterns),
            decision_notes=command.decision_notes,
            theory_notes=command.theory_notes,
            notes=command.notes,
            outcome="in_progress",
            started_at=self.now_factory(),
        )
        self.repository.add_session(session)

        events: list[SessionClosed | SessionOpened] = [
            SessionClosed(s) for s in superseded
        ]
        events.append(SessionOpened(session))
        return events

    def _handle_close_session(self, command: CloseSession):
        session = self._require_session(command.session_id)
        updated = self._apply_session_close(
            session=session,
            outcome=command.outcome,
            summary=command.summary,
            tokens=command.tokens,
            rule_set_version=command.rule_set_version,
            instructions_fingerprint=command.instructions_fingerprint,
            skills_used=command.skills_used,
            tool_calls_summary=command.tool_calls_summary,
            tool_calls_summary_tokens=command.tool_calls_summary_tokens,
            design_patterns=command.design_patterns,
            decision_notes=command.decision_notes,
            theory_notes=command.theory_notes,
            notes=command.notes,
            artifacts=command.artifacts,
        )
        return [SessionClosed(updated)]

    def _handle_log_tokens(self, command: LogTokens):
        session = self._resolve_log_tokens_target(command)
        if command.replace:
            updated = replace(
                session,
                tokens_in=command.tokens_in,
                tokens_out=command.tokens_out,
                tokens_cache_read=command.cache_read,
                tokens_cache_write=command.cache_write,
                notes=self._append_note(session.notes, command.note),
            )
        else:
            updated = replace(
                session,
                tokens_in=session.tokens_in + command.tokens_in,
                tokens_out=session.tokens_out + command.tokens_out,
                tokens_cache_read=session.tokens_cache_read + command.cache_read,
                tokens_cache_write=session.tokens_cache_write + command.cache_write,
                notes=self._append_note(session.notes, command.note),
            )
        self.repository.update_session(updated)
        return [TokensLogged(updated)]

    def _resolve_log_tokens_target(self, command: LogTokens):
        if (command.session_id is None) == (command.agent_id is None):
            raise ValueError(
                "log_tokens requires exactly one of session_id or agent_id."
            )
        if command.session_id is not None:
            return self._require_session(command.session_id)
        open_sessions = self.repository.list_open_sessions(agent_id=command.agent_id)
        if not open_sessions:
            raise ValueError(
                f"No open session for agent_id={command.agent_id!r}; "
                "open_session before logging tokens by agent."
            )
        # open_session auto-supersedes prior opens for the same agent, so
        # there should be at most one. Take the most recent in case of a
        # repository edge case.
        return max(open_sessions, key=lambda s: (s.started_at, s.id))

    def _handle_log_tool_calls_summary(self, command: LogToolCallsSummary):
        session = self._require_session(command.session_id)
        canonical_summary, _ = _canonicalize_tool_counts(
            dict(command.tool_calls_summary)
        )
        updated = replace(
            session,
            tool_calls_summary=self._merge_counts(
                session.tool_calls_summary, canonical_summary
            ),
            tool_calls_summary_tokens=(
                session.tool_calls_summary_tokens + (command.tokens or TokenUsage())
            ),
            notes=self._append_note(session.notes, command.note),
        )
        self.repository.update_session(updated)
        return [ToolCallsSummaryLogged(updated)]

    def _handle_sweep_stale_sessions(self, command: SweepStaleSessions):
        """Drop-off recovery floor: close sessions that have been open since
        before ``cutoff_iso`` (lexicographic comparison on the ISO-8601
        ``started_at``). Outcome = ``abandoned``. Catches the case where
        no agent ever comes back."""
        candidates = self.repository.list_open_sessions()
        closed: list[Session] = []
        for session in candidates:
            if session.started_at < command.cutoff_iso:
                updated = self._supersede_session(
                    session,
                    f"Auto-closed by sweep_stale_sessions; started "
                    f"{session.started_at}, cutoff {command.cutoff_iso}.",
                    outcome="abandoned",
                )
                closed.append(updated)
        return [StaleSessionsSwept(closed)]

    def _handle_request_feature(self, command: RequestFeature):
        now = self.now_factory()
        feature_request = FeatureRequest(
            id=self._new_id("fr"),
            title=command.title,
            kind=command.kind,
            detail=command.detail,
            task_id=command.task_id,
            session_id=command.session_id,
            agent_id=command.agent_id,
            model_name=command.model_name,
            notes=command.notes,
            created_at=now,
            updated_at=now,
        )
        self.repository.add_feature_request(feature_request)
        return [FeatureRequested(feature_request)]

    _FEATURE_REQUEST_RESOLUTIONS = frozenset(
        {"discarded", "already_complete", "converted_to_task"}
    )

    def _handle_resolve_feature_request(self, command: ResolveFeatureRequest):
        if command.resolution not in self._FEATURE_REQUEST_RESOLUTIONS:
            raise ValueError(
                f"Unknown resolution {command.resolution!r}; expected one of "
                f"{sorted(self._FEATURE_REQUEST_RESOLUTIONS)}."
            )
        feature_request = self.repository.get_feature_request(
            command.feature_request_id
        )
        if feature_request is None:
            raise ValueError(f"Feature request {command.feature_request_id} not found.")
        if feature_request.status == "resolved":
            raise ValueError(
                f"Feature request {command.feature_request_id} is already resolved "
                f"({feature_request.resolution!r})."
            )
        resolution_task_id: str | None = None
        if command.resolution == "converted_to_task":
            if not command.task_id:
                raise ValueError(
                    "task_id is required when resolution is 'converted_to_task'."
                )
            if self.repository.get_task(command.task_id) is None:
                raise ValueError(f"Task {command.task_id} not found.")
            resolution_task_id = command.task_id
        elif command.task_id:
            raise ValueError(
                "task_id is only accepted when resolution is 'converted_to_task'."
            )
        updated = replace(
            feature_request,
            status="resolved",
            resolution=command.resolution,
            resolution_task_id=resolution_task_id,
            notes=self._append_note(feature_request.notes, command.note),
            updated_at=self.now_factory(),
        )
        self.repository.update_feature_request(updated)
        return [FeatureRequestResolved(updated)]

    def _close_task_session(
        self,
        session_id: str,
        outcome: str,
        summary: str,
        tokens: TokenUsage | None = None,
        rule_set_version: str | None = None,
        instructions_fingerprint: str | None = None,
        skills_used: list[str] | None = None,
        tool_calls_summary: dict[str, int] | None = None,
        tool_calls_summary_tokens: TokenUsage | None = None,
        design_patterns: list[str] | None = None,
        decision_notes: str | None = None,
        theory_notes: str | None = None,
        notes: str | None = None,
        artifacts: list[str] | None = None,
    ) -> Session:
        session = self._require_session(session_id)
        return self._apply_session_close(
            session,
            outcome,
            summary,
            tokens,
            rule_set_version,
            instructions_fingerprint,
            skills_used or [],
            tool_calls_summary or {},
            tool_calls_summary_tokens,
            design_patterns or [],
            decision_notes,
            theory_notes,
            notes,
            artifacts or [],
        )

    def _close_sessions_for_completion(
        self,
        task_id: str,
        session_id: str | None,
        summary: str,
        tokens: TokenUsage | None,
        artifacts: list[str],
    ) -> list[Session]:
        """Close the session(s) covered by a ``complete_task`` call.

        - If ``session_id`` is supplied, validate that the session belongs
          to ``task_id`` (refusing the cross-task orphaning that produced
          PR #32's stale opens) and close it. Already-closed sessions are
          returned unchanged.
        - If ``session_id`` is omitted, close every currently-open session
          for the task. The auto-close path is the recovery shape: the
          next ``complete_task`` cleans up whatever was left dangling.

        Tokens and artifacts attribute to the first session closed; the
        rest get just the completion summary.
        """
        if session_id is not None:
            session = self._require_session(session_id)
            if session.task_id != task_id:
                raise ValueError(
                    f"session {session_id} belongs to task "
                    f"{session.task_id}, not {task_id}; refusing to close "
                    f"it as part of completing the wrong task."
                )
            if session.ended_at is not None:
                return [session]
            updated = self._apply_session_close(
                session,
                outcome="completed",
                summary=summary,
                tokens=tokens,
                rule_set_version=None,
                instructions_fingerprint=None,
                skills_used=[],
                tool_calls_summary={},
                tool_calls_summary_tokens=None,
                design_patterns=[],
                decision_notes=None,
                theory_notes=None,
                notes=None,
                artifacts=artifacts,
            )
            return [updated]

        open_sessions = self.repository.list_open_sessions(task_id=task_id)
        closed: list[Session] = []
        for session in open_sessions:
            primary = not closed
            updated = self._apply_session_close(
                session,
                outcome="completed",
                summary=summary,
                tokens=tokens if primary else None,
                rule_set_version=None,
                instructions_fingerprint=None,
                skills_used=[],
                tool_calls_summary={},
                tool_calls_summary_tokens=None,
                design_patterns=[],
                decision_notes=None,
                theory_notes=None,
                notes=None,
                artifacts=artifacts if primary else [],
            )
            closed.append(updated)
        return closed

    def _supersede_session(
        self,
        session: Session,
        summary: str,
        outcome: str = "superseded",
    ) -> Session:
        """Minimal close that stamps an outcome + synthetic summary.

        Used by the drop-off recovery paths in ``open_session`` and
        ``sweep_stale_sessions`` where the session being closed has no
        clean owner-supplied close payload.
        """
        return self._apply_session_close(
            session,
            outcome=outcome,
            summary=summary,
            tokens=None,
            rule_set_version=None,
            instructions_fingerprint=None,
            skills_used=[],
            tool_calls_summary={},
            tool_calls_summary_tokens=None,
            design_patterns=[],
            decision_notes=None,
            theory_notes=None,
            notes=None,
            artifacts=[],
        )

    def _apply_session_close(
        self,
        session: Session,
        outcome: str,
        summary: str | None,
        tokens: TokenUsage | None,
        rule_set_version: str | None,
        instructions_fingerprint: str | None,
        skills_used: list[str],
        tool_calls_summary: dict[str, int],
        tool_calls_summary_tokens: TokenUsage | None,
        design_patterns: list[str],
        decision_notes: str | None,
        theory_notes: str | None,
        notes: str | None,
        artifacts: list[str],
    ) -> Session:
        token_usage = tokens or TokenUsage()
        canonical_summary, _ = _canonicalize_tool_counts(dict(tool_calls_summary))
        updated = replace(
            session,
            outcome=outcome,
            summary=summary,
            rule_set_version=rule_set_version or session.rule_set_version,
            instructions_fingerprint=(
                instructions_fingerprint or session.instructions_fingerprint
            ),
            skills_used=self._merge_unique(session.skills_used, skills_used),
            tool_calls_summary=self._merge_counts(
                session.tool_calls_summary, canonical_summary
            ),
            tool_calls_summary_tokens=(
                session.tool_calls_summary_tokens
                + (tool_calls_summary_tokens or TokenUsage())
            ),
            design_patterns=self._merge_unique(
                session.design_patterns, design_patterns
            ),
            decision_notes=self._append_note(session.decision_notes, decision_notes),
            theory_notes=self._append_note(session.theory_notes, theory_notes),
            notes=self._append_note(session.notes, notes),
            artifacts=list(artifacts),
            ended_at=self.now_factory(),
            tokens_in=session.tokens_in + token_usage.tokens_in,
            tokens_out=session.tokens_out + token_usage.tokens_out,
            tokens_cache_read=session.tokens_cache_read + token_usage.tokens_cache_read,
            tokens_cache_write=session.tokens_cache_write
            + token_usage.tokens_cache_write,
        )
        self.repository.update_session(updated)
        return updated

    def _next_task(self, hint_filter: str | None) -> Task | None:
        tasks = self.repository.list_tasks(status="ready")
        candidates = [
            task
            for task in tasks
            if self._dependencies_satisfied(task.depends_on)
            and (hint_filter is None or task.agent_hint == hint_filter)
        ]
        if not candidates:
            return None
        return min(
            candidates, key=lambda task: (-task.priority, task.created_at, task.id)
        )

    def _promote_unblocked_tasks(self, completed_task_id: str) -> list[str]:
        promoted: list[str] = []
        for task in self.repository.list_tasks():
            if task.id == completed_task_id:
                continue

            should_promote = False
            if task.status == "blocked" and task.depends_on:
                should_promote = self._dependencies_satisfied(task.depends_on)

            if task.status == "blocked":
                should_promote = should_promote or self._children_done(task.id)

            if should_promote:
                updated = replace(task, status="ready", updated_at=self.now_factory())
                self.repository.update_task(updated)
                self._record_transition(updated, task.status, updated.status, "system")
                promoted.append(task.id)
        return promoted

    def _children_done(self, parent_id: str) -> bool:
        children = [
            task for task in self.repository.list_tasks() if task.parent_id == parent_id
        ]
        return bool(children) and all(child.status == "done" for child in children)

    def _dependencies_satisfied(self, depends_on: list[str]) -> bool:
        if not depends_on:
            return True
        for task_id in depends_on:
            task = self.repository.get_task(task_id)
            if task is None or task.status != "done":
                return False
        return True

    def _record_transition(
        self,
        task: Task,
        from_status: str | None,
        to_status: str | None,
        actor: str,
        note: str | None = None,
    ) -> None:
        event = TaskEvent(
            task_id=task.id,
            from_status=from_status,
            to_status=to_status,
            actor=actor,
            note=note,
            created_at=self.now_factory(),
        )
        self.repository.add_task_event(event)

    def _require_task(self, task_id: str) -> Task:
        task = self.repository.get_task(task_id)
        if task is None:
            raise KeyError(f"Unknown task: {task_id}")
        return task

    def _require_session(self, session_id: str) -> Session:
        session = self.repository.get_session(session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        return session

    @staticmethod
    def _append_note(existing: str | None, note: str | None) -> str | None:
        if not note:
            return existing
        if not existing:
            return note
        return f"{existing}\n\n{note}"

    @staticmethod
    def _merge_unique(existing: list[str], new_items: list[str]) -> list[str]:
        merged = list(existing)
        for item in new_items:
            if item not in merged:
                merged.append(item)
        return merged

    @staticmethod
    def _merge_counts(
        existing: dict[str, int], new_items: dict[str, int]
    ) -> dict[str, int]:
        merged = dict(existing)
        for key, value in new_items.items():
            merged[key] = merged.get(key, 0) + value
        return merged

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{token_urlsafe(4).lower()}"

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
