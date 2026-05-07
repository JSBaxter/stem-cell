from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TokenUsage:
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cache_read: int = 0
    tokens_cache_write: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            tokens_in=self.tokens_in + other.tokens_in,
            tokens_out=self.tokens_out + other.tokens_out,
            tokens_cache_read=self.tokens_cache_read + other.tokens_cache_read,
            tokens_cache_write=self.tokens_cache_write + other.tokens_cache_write,
        )


@dataclass(slots=True)
class Task:
    id: str
    title: str
    description: str | None = None
    status: str = "idea"
    priority: int = 50
    parent_id: str | None = None
    depends_on: list[str] = field(default_factory=list)
    relevant_files: list[str] = field(default_factory=list)
    relevant_services: list[str] = field(default_factory=list)
    agent_hint: str | None = None
    notes: str | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class Session:
    id: str
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
    tool_calls_summary_tokens: TokenUsage = field(default_factory=TokenUsage)
    design_patterns: list[str] = field(default_factory=list)
    decision_notes: str | None = None
    theory_notes: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cache_read: int = 0
    tokens_cache_write: int = 0
    outcome: str | None = None
    summary: str | None = None
    notes: str | None = None
    artifacts: list[str] = field(default_factory=list)
    started_at: str = ""
    ended_at: str | None = None

    def token_usage(self) -> TokenUsage:
        return TokenUsage(
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            tokens_cache_read=self.tokens_cache_read,
            tokens_cache_write=self.tokens_cache_write,
        )


@dataclass(slots=True)
class TaskEvent:
    task_id: str
    from_status: str | None
    to_status: str | None
    actor: str
    note: str | None = None
    created_at: str = ""
    id: int | None = None


@dataclass(slots=True)
class FeatureRequest:
    id: str
    title: str
    kind: str
    detail: str
    status: str = "open"
    task_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    model_name: str | None = None
    notes: str | None = None
    resolution: str | None = None
    resolution_task_id: str | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class TaskDetail:
    task: Task
    sessions: list[Session]
    token_rollup: TokenUsage
    events: list[TaskEvent]


@dataclass(slots=True)
class HealthReport:
    ok: bool
    db_path: str | None
    sqlite_version: str
    schema_ready: bool
    task_count: int
    session_count: int
    feature_request_count: int
    checked_at: str


@dataclass(slots=True)
class QueueStats:
    task_count_total: int
    task_counts_by_status: dict[str, int]
    session_count_total: int
    sessions_by_stage: dict[str, int]
    open_session_count: int
    feature_request_count_total: int
    feature_requests_by_status: dict[str, int]
    feature_requests_by_kind: dict[str, int]
    token_totals: TokenUsage
    tool_calls_summary_totals: dict[str, int]
    tool_calls_summary_token_totals: TokenUsage


@dataclass(slots=True)
class OpenSessionView:
    session_id: str
    agent_id: str
    stage: str
    started_at: str
    task_id: str
    task_title: str
    task_status: str


@dataclass(slots=True)
class SessionNotesView:
    session_id: str
    task_id: str
    agent_id: str
    started_at: str
    ended_at: str | None
    decision_notes: str | None
    theory_notes: str | None
    design_patterns: list[str]
    summary: str | None


@dataclass(slots=True)
class AgentActivity:
    agent_id: str
    session_count: int
    open_session_count: int
    sessions_by_outcome: dict[str, int]
    distinct_tasks: int
    tasks_completed: int
    token_totals: TokenUsage
    tool_calls: dict[str, int]


@dataclass(slots=True)
class CanonicalToolCalls:
    counts: dict[str, int]
    aliases: dict[str, str]
