from __future__ import annotations

from dataclasses import dataclass

from .models import FeatureRequest, Session, Task


@dataclass(slots=True)
class IdeaAdded:
    task: Task


@dataclass(slots=True)
class TaskScoped:
    task: Task


@dataclass(slots=True)
class TaskClaimed:
    task: Task
    session: Session


@dataclass(slots=True)
class ClaimFailed:
    reason: str


@dataclass(slots=True)
class TaskCompleted:
    task: Task
    sessions: list[Session]


@dataclass(slots=True)
class DependentsUnblocked:
    task_ids: list[str]


@dataclass(slots=True)
class TaskFailed:
    task: Task
    session: Session


@dataclass(slots=True)
class TaskRetried:
    task: Task


@dataclass(slots=True)
class TaskBlocked:
    task: Task
    session: Session


@dataclass(slots=True)
class TaskSplit:
    parent: Task
    children: list[Task]


@dataclass(slots=True)
class SessionOpened:
    session: Session


@dataclass(slots=True)
class SessionClosed:
    session: Session


@dataclass(slots=True)
class TokensLogged:
    session: Session


@dataclass(slots=True)
class ToolCallsSummaryLogged:
    session: Session


@dataclass(slots=True)
class FeatureRequested:
    feature_request: FeatureRequest


@dataclass(slots=True)
class FeatureRequestResolved:
    feature_request: FeatureRequest


@dataclass(slots=True)
class StaleSessionsSwept:
    """Emitted by ``sweep_stale_sessions`` with the sessions auto-closed."""

    sessions: list[Session]
