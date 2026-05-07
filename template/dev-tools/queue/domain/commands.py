from __future__ import annotations

from dataclasses import dataclass, field

from .models import TokenUsage


@dataclass(slots=True)
class AddIdea:
    title: str
    notes: str | None = None


@dataclass(slots=True)
class ScopeTask:
    task_id: str
    description: str
    context: str
    priority: int
    depends_on: list[str] = field(default_factory=list)
    relevant_files: list[str] = field(default_factory=list)
    relevant_services: list[str] = field(default_factory=list)
    agent_hint: str | None = None


@dataclass(slots=True)
class ClaimTask:
    agent_id: str
    hint_filter: str | None = None


@dataclass(slots=True)
class CompleteTask:
    task_id: str
    summary: str
    session_id: str | None = None
    artifacts: list[str] = field(default_factory=list)
    tokens: TokenUsage | None = None


@dataclass(slots=True)
class FailTask:
    task_id: str
    session_id: str
    reason: str
    retry: bool = False
    tokens: TokenUsage | None = None


@dataclass(slots=True)
class BlockTask:
    task_id: str
    session_id: str
    reason: str
    tokens: TokenUsage | None = None


@dataclass(slots=True)
class SubtaskInput:
    title: str
    description: str | None = None
    priority: int = 50
    depends_on: list[str] = field(default_factory=list)
    relevant_files: list[str] = field(default_factory=list)
    relevant_services: list[str] = field(default_factory=list)
    agent_hint: str | None = None
    notes: str | None = None


@dataclass(slots=True)
class SplitTask:
    parent_id: str
    subtasks: list[SubtaskInput]


@dataclass(slots=True)
class AddNote:
    task_id: str
    note: str


@dataclass(slots=True)
class OpenSession:
    task_id: str
    stage: str
    agent_id: str
    model_name: str | None = None
    model_family: str | None = None
    model_version: str | None = None
    operating_mode: str | None = None
    rule_set_version: str | None = None
    instructions_fingerprint: str | None = None
    session_ref: str | None = None
    skills_used: list[str] = field(default_factory=list)
    tool_calls_summary: dict[str, int] = field(default_factory=dict)
    tool_calls_summary_tokens: TokenUsage | None = None
    design_patterns: list[str] = field(default_factory=list)
    decision_notes: str | None = None
    theory_notes: str | None = None
    notes: str | None = None


@dataclass(slots=True)
class CloseSession:
    session_id: str
    outcome: str
    summary: str | None = None
    tokens: TokenUsage | None = None
    rule_set_version: str | None = None
    instructions_fingerprint: str | None = None
    skills_used: list[str] = field(default_factory=list)
    tool_calls_summary: dict[str, int] = field(default_factory=dict)
    tool_calls_summary_tokens: TokenUsage | None = None
    design_patterns: list[str] = field(default_factory=list)
    decision_notes: str | None = None
    theory_notes: str | None = None
    notes: str | None = None
    artifacts: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LogTokens:
    """Attribute token usage to a session.

    Either ``session_id`` or ``agent_id`` must be supplied (not both).
    ``agent_id`` resolves to the agent's currently-open session, since
    ``open_session`` enforces one open session per agent. With
    ``replace=False`` the values add to existing totals; with
    ``replace=True`` they overwrite — useful for hooks that re-read a
    full transcript on each fire and want idempotent re-runs.
    """

    session_id: str | None = None
    agent_id: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    cache_write: int = 0
    note: str | None = None
    replace: bool = False


@dataclass(slots=True)
class LogToolCallsSummary:
    session_id: str
    tool_calls_summary: dict[str, int] = field(default_factory=dict)
    tokens: TokenUsage | None = None
    note: str | None = None


@dataclass(slots=True)
class SweepStaleSessions:
    """Close sessions that have been open since before ``cutoff_iso``.

    Each closed session gets ``outcome="abandoned"`` and a synthetic
    summary noting the sweep.
    """

    cutoff_iso: str


@dataclass(slots=True)
class RequestFeature:
    title: str
    kind: str
    detail: str
    task_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    model_name: str | None = None
    notes: str | None = None


@dataclass(slots=True)
class ResolveFeatureRequest:
    """Close out a feature request as discarded, already-complete, or
    converted to a task. ``task_id`` is required when
    ``resolution == "converted_to_task"`` and must reference an existing
    task; the link is stored on ``FeatureRequest.resolution_task_id``
    (separate from the originating ``task_id`` recorded at request
    time)."""

    feature_request_id: str
    resolution: str
    task_id: str | None = None
    note: str | None = None
