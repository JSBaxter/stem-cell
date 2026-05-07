from __future__ import annotations

from dataclasses import replace

from domain.models import (
    FeatureRequest,
    HealthReport,
    QueueStats,
    Session,
    Task,
    TaskEvent,
    TokenUsage,
)


class InMemoryRepository:
    def __init__(self, db_path: str | None = ":memory:") -> None:
        self.db_path = db_path
        self.tasks: dict[str, Task] = {}
        self.sessions: dict[str, Session] = {}
        self.task_events: list[TaskEvent] = []
        self.feature_requests: dict[str, FeatureRequest] = {}
        self._event_id = 1

    def add_task(self, task: Task) -> None:
        self.tasks[task.id] = replace(task)

    def update_task(self, task: Task) -> None:
        self.tasks[task.id] = replace(task)

    def get_task(self, task_id: str) -> Task | None:
        task = self.tasks.get(task_id)
        return replace(task) if task is not None else None

    def list_tasks(self, status: str | None = None) -> list[Task]:
        tasks = [replace(task) for task in self.tasks.values()]
        if status is not None:
            tasks = [task for task in tasks if task.status == status]
        return tasks

    def add_session(self, session: Session) -> None:
        self.sessions[session.id] = replace(session)

    def update_session(self, session: Session) -> None:
        self.sessions[session.id] = replace(session)

    def get_session(self, session_id: str) -> Session | None:
        session = self.sessions.get(session_id)
        return replace(session) if session is not None else None

    def list_sessions(self, task_id: str | None = None) -> list[Session]:
        sessions = [replace(session) for session in self.sessions.values()]
        if task_id is not None:
            sessions = [session for session in sessions if session.task_id == task_id]
        return sessions

    def list_open_sessions(
        self, task_id: str | None = None, agent_id: str | None = None
    ) -> list[Session]:
        sessions = [
            replace(session)
            for session in self.sessions.values()
            if session.ended_at is None
        ]
        if task_id is not None:
            sessions = [session for session in sessions if session.task_id == task_id]
        if agent_id is not None:
            sessions = [session for session in sessions if session.agent_id == agent_id]
        sessions.sort(key=lambda s: (s.started_at, s.id))
        return sessions

    def add_task_event(self, event: TaskEvent) -> TaskEvent:
        stored = replace(event, id=self._event_id)
        self._event_id += 1
        self.task_events.append(stored)
        return replace(stored)

    def list_task_events(self, task_id: str) -> list[TaskEvent]:
        return [
            replace(event) for event in self.task_events if event.task_id == task_id
        ]

    def add_feature_request(self, feature_request: FeatureRequest) -> None:
        self.feature_requests[feature_request.id] = replace(feature_request)

    def update_feature_request(self, feature_request: FeatureRequest) -> None:
        self.feature_requests[feature_request.id] = replace(feature_request)

    def get_feature_request(self, feature_request_id: str) -> FeatureRequest | None:
        feature_request = self.feature_requests.get(feature_request_id)
        return replace(feature_request) if feature_request is not None else None

    def list_feature_requests(self, status: str | None = None) -> list[FeatureRequest]:
        feature_requests = [
            replace(feature_request)
            for feature_request in self.feature_requests.values()
        ]
        if status is not None:
            feature_requests = [
                feature_request
                for feature_request in feature_requests
                if feature_request.status == status
            ]
        return feature_requests

    def health_report(self, checked_at: str) -> HealthReport:
        return HealthReport(
            ok=True,
            db_path=self.db_path,
            sqlite_version="in-memory",
            schema_ready=True,
            task_count=len(self.tasks),
            session_count=len(self.sessions),
            feature_request_count=len(self.feature_requests),
            checked_at=checked_at,
        )

    def queue_stats(self) -> QueueStats:
        task_counts_by_status: dict[str, int] = {}
        for task in self.tasks.values():
            task_counts_by_status[task.status] = (
                task_counts_by_status.get(task.status, 0) + 1
            )

        sessions_by_stage: dict[str, int] = {}
        open_session_count = 0
        token_totals = TokenUsage()
        tool_calls_summary_totals: dict[str, int] = {}
        tool_calls_summary_token_totals = TokenUsage()
        for session in self.sessions.values():
            sessions_by_stage[session.stage] = (
                sessions_by_stage.get(session.stage, 0) + 1
            )
            if session.ended_at is None or session.outcome == "in_progress":
                open_session_count += 1
            token_totals = token_totals + session.token_usage()
            tool_calls_summary_token_totals = (
                tool_calls_summary_token_totals + session.tool_calls_summary_tokens
            )
            for key, value in session.tool_calls_summary.items():
                tool_calls_summary_totals[key] = (
                    tool_calls_summary_totals.get(key, 0) + value
                )

        feature_requests_by_status: dict[str, int] = {}
        feature_requests_by_kind: dict[str, int] = {}
        for feature_request in self.feature_requests.values():
            feature_requests_by_status[feature_request.status] = (
                feature_requests_by_status.get(feature_request.status, 0) + 1
            )
            feature_requests_by_kind[feature_request.kind] = (
                feature_requests_by_kind.get(feature_request.kind, 0) + 1
            )

        return QueueStats(
            task_count_total=len(self.tasks),
            task_counts_by_status=task_counts_by_status,
            session_count_total=len(self.sessions),
            sessions_by_stage=sessions_by_stage,
            open_session_count=open_session_count,
            feature_request_count_total=len(self.feature_requests),
            feature_requests_by_status=feature_requests_by_status,
            feature_requests_by_kind=feature_requests_by_kind,
            token_totals=token_totals,
            tool_calls_summary_totals=tool_calls_summary_totals,
            tool_calls_summary_token_totals=tool_calls_summary_token_totals,
        )


class FakeClock:
    def __init__(self) -> None:
        self._tick = 0

    def now(self) -> str:
        self._tick += 1
        return f"2026-04-24T12:00:{self._tick:02d}+00:00"
