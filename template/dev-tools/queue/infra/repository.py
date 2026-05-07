from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from domain.models import (
    FeatureRequest,
    HealthReport,
    QueueStats,
    Session,
    Task,
    TaskEvent,
    TokenUsage,
)


class SQLiteRepository:
    def __init__(
        self, connection: sqlite3.Connection, db_path: str | None = None
    ) -> None:
        self.connection = connection
        self.db_path = db_path
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    @classmethod
    def connect(cls, db_path: str | Path) -> "SQLiteRepository":
        connection = sqlite3.connect(str(db_path), check_same_thread=False)
        repository = cls(connection, db_path=str(db_path))
        repository.init_schema()
        return repository

    def init_schema(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        self.connection.executescript(schema_path.read_text())
        self._migrate_sessions_columns()
        self._migrate_feature_requests_columns()
        self.connection.commit()

    def _migrate_sessions_columns(self) -> None:
        """Idempotent ADD COLUMN for fields appended after first release.

        Live databases predate the columns added in schema.sql; SQLite's
        CREATE TABLE IF NOT EXISTS won't grow them. Probe the existing
        column list and ALTER what's missing.
        """
        existing = {
            row[1] for row in self.connection.execute("PRAGMA table_info(sessions)")
        }
        for column in ("model_family", "model_version"):
            if column not in existing:
                self.connection.execute(
                    f"ALTER TABLE sessions ADD COLUMN {column} TEXT"
                )

    def _migrate_feature_requests_columns(self) -> None:
        existing = {
            row[1]
            for row in self.connection.execute("PRAGMA table_info(feature_requests)")
        }
        if "resolution" not in existing:
            self.connection.execute(
                "ALTER TABLE feature_requests ADD COLUMN resolution TEXT"
            )
        if "resolution_task_id" not in existing:
            self.connection.execute(
                "ALTER TABLE feature_requests "
                "ADD COLUMN resolution_task_id TEXT REFERENCES tasks(id)"
            )

    def add_task(self, task: Task) -> None:
        self.connection.execute(
            """
            INSERT INTO tasks (
                id, title, description, status, priority, parent_id,
                depends_on, relevant_files, relevant_services,
                agent_hint, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.id,
                task.title,
                task.description,
                task.status,
                task.priority,
                task.parent_id,
                self._json(task.depends_on),
                self._json(task.relevant_files),
                self._json(task.relevant_services),
                task.agent_hint,
                task.notes,
                task.created_at,
                task.updated_at,
            ),
        )
        self.connection.commit()

    def update_task(self, task: Task) -> None:
        self.connection.execute(
            """
            UPDATE tasks
            SET title = ?,
                description = ?,
                status = ?,
                priority = ?,
                parent_id = ?,
                depends_on = ?,
                relevant_files = ?,
                relevant_services = ?,
                agent_hint = ?,
                notes = ?,
                created_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                task.title,
                task.description,
                task.status,
                task.priority,
                task.parent_id,
                self._json(task.depends_on),
                self._json(task.relevant_files),
                self._json(task.relevant_services),
                task.agent_hint,
                task.notes,
                task.created_at,
                task.updated_at,
                task.id,
            ),
        )
        self.connection.commit()

    def get_task(self, task_id: str) -> Task | None:
        row = self.connection.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        return self._task_from_row(row) if row is not None else None

    def list_tasks(self, status: str | None = None) -> list[Task]:
        if status is None:
            rows = self.connection.execute(
                "SELECT * FROM tasks ORDER BY created_at, id"
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at, id",
                (status,),
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def add_session(self, session: Session) -> None:
        self.connection.execute(
            """
            INSERT INTO sessions (
                id, task_id, stage, agent_id, model_name,
                model_family, model_version, operating_mode,
                rule_set_version, instructions_fingerprint,
                session_ref, skills_used, tool_calls_summary,
                tool_calls_summary_tokens_in, tool_calls_summary_tokens_out,
                tool_calls_summary_cache_read, tool_calls_summary_cache_write,
                design_patterns, decision_notes,
                theory_notes, tokens_in, tokens_out, tokens_cache_read,
                tokens_cache_write, outcome, summary, notes, artifacts,
                started_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.task_id,
                session.stage,
                session.agent_id,
                session.model_name,
                session.model_family,
                session.model_version,
                session.operating_mode,
                session.rule_set_version,
                session.instructions_fingerprint,
                session.session_ref,
                self._json(session.skills_used),
                json.dumps(session.tool_calls_summary),
                session.tool_calls_summary_tokens.tokens_in,
                session.tool_calls_summary_tokens.tokens_out,
                session.tool_calls_summary_tokens.tokens_cache_read,
                session.tool_calls_summary_tokens.tokens_cache_write,
                self._json(session.design_patterns),
                session.decision_notes,
                session.theory_notes,
                session.tokens_in,
                session.tokens_out,
                session.tokens_cache_read,
                session.tokens_cache_write,
                session.outcome,
                session.summary,
                session.notes,
                self._json(session.artifacts),
                session.started_at,
                session.ended_at,
            ),
        )
        self.connection.commit()

    def update_session(self, session: Session) -> None:
        self.connection.execute(
            """
            UPDATE sessions
            SET task_id = ?,
                stage = ?,
                agent_id = ?,
                model_name = ?,
                model_family = ?,
                model_version = ?,
                operating_mode = ?,
                rule_set_version = ?,
                instructions_fingerprint = ?,
                session_ref = ?,
                skills_used = ?,
                tool_calls_summary = ?,
                tool_calls_summary_tokens_in = ?,
                tool_calls_summary_tokens_out = ?,
                tool_calls_summary_cache_read = ?,
                tool_calls_summary_cache_write = ?,
                design_patterns = ?,
                decision_notes = ?,
                theory_notes = ?,
                tokens_in = ?,
                tokens_out = ?,
                tokens_cache_read = ?,
                tokens_cache_write = ?,
                outcome = ?,
                summary = ?,
                notes = ?,
                artifacts = ?,
                started_at = ?,
                ended_at = ?
            WHERE id = ?
            """,
            (
                session.task_id,
                session.stage,
                session.agent_id,
                session.model_name,
                session.model_family,
                session.model_version,
                session.operating_mode,
                session.rule_set_version,
                session.instructions_fingerprint,
                session.session_ref,
                self._json(session.skills_used),
                json.dumps(session.tool_calls_summary),
                session.tool_calls_summary_tokens.tokens_in,
                session.tool_calls_summary_tokens.tokens_out,
                session.tool_calls_summary_tokens.tokens_cache_read,
                session.tool_calls_summary_tokens.tokens_cache_write,
                self._json(session.design_patterns),
                session.decision_notes,
                session.theory_notes,
                session.tokens_in,
                session.tokens_out,
                session.tokens_cache_read,
                session.tokens_cache_write,
                session.outcome,
                session.summary,
                session.notes,
                self._json(session.artifacts),
                session.started_at,
                session.ended_at,
                session.id,
            ),
        )
        self.connection.commit()

    def get_session(self, session_id: str) -> Session | None:
        row = self.connection.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        return self._session_from_row(row) if row is not None else None

    def list_sessions(self, task_id: str | None = None) -> list[Session]:
        if task_id is None:
            rows = self.connection.execute(
                "SELECT * FROM sessions ORDER BY started_at, id"
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM sessions WHERE task_id = ? ORDER BY started_at, id",
                (task_id,),
            ).fetchall()
        return [self._session_from_row(row) for row in rows]

    def list_open_sessions(
        self, task_id: str | None = None, agent_id: str | None = None
    ) -> list[Session]:
        clauses = ["ended_at IS NULL"]
        params: list[str] = []
        if task_id is not None:
            clauses.append("task_id = ?")
            params.append(task_id)
        if agent_id is not None:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        sql = (
            "SELECT * FROM sessions WHERE "
            + " AND ".join(clauses)
            + " ORDER BY started_at, id"
        )
        rows = self.connection.execute(sql, params).fetchall()
        return [self._session_from_row(row) for row in rows]

    def add_task_event(self, event: TaskEvent) -> TaskEvent:
        cursor = self.connection.execute(
            """
            INSERT INTO task_events (task_id, from_status, to_status, actor, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.task_id,
                event.from_status,
                event.to_status,
                event.actor,
                event.note,
                event.created_at,
            ),
        )
        self.connection.commit()
        return TaskEvent(
            id=cursor.lastrowid,
            task_id=event.task_id,
            from_status=event.from_status,
            to_status=event.to_status,
            actor=event.actor,
            note=event.note,
            created_at=event.created_at,
        )

    def list_task_events(self, task_id: str) -> list[TaskEvent]:
        rows = self.connection.execute(
            "SELECT * FROM task_events WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()
        return [self._task_event_from_row(row) for row in rows]

    def add_feature_request(self, feature_request: FeatureRequest) -> None:
        self.connection.execute(
            """
            INSERT INTO feature_requests (
                id, title, kind, detail, status, task_id, session_id,
                agent_id, model_name, notes, resolution,
                resolution_task_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feature_request.id,
                feature_request.title,
                feature_request.kind,
                feature_request.detail,
                feature_request.status,
                feature_request.task_id,
                feature_request.session_id,
                feature_request.agent_id,
                feature_request.model_name,
                feature_request.notes,
                feature_request.resolution,
                feature_request.resolution_task_id,
                feature_request.created_at,
                feature_request.updated_at,
            ),
        )
        self.connection.commit()

    def update_feature_request(self, feature_request: FeatureRequest) -> None:
        self.connection.execute(
            """
            UPDATE feature_requests
            SET title = ?,
                kind = ?,
                detail = ?,
                status = ?,
                task_id = ?,
                session_id = ?,
                agent_id = ?,
                model_name = ?,
                notes = ?,
                resolution = ?,
                resolution_task_id = ?,
                created_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                feature_request.title,
                feature_request.kind,
                feature_request.detail,
                feature_request.status,
                feature_request.task_id,
                feature_request.session_id,
                feature_request.agent_id,
                feature_request.model_name,
                feature_request.notes,
                feature_request.resolution,
                feature_request.resolution_task_id,
                feature_request.created_at,
                feature_request.updated_at,
                feature_request.id,
            ),
        )
        self.connection.commit()

    def get_feature_request(self, feature_request_id: str) -> FeatureRequest | None:
        row = self.connection.execute(
            "SELECT * FROM feature_requests WHERE id = ?",
            (feature_request_id,),
        ).fetchone()
        return self._feature_request_from_row(row) if row is not None else None

    def list_feature_requests(self, status: str | None = None) -> list[FeatureRequest]:
        if status is None:
            rows = self.connection.execute(
                "SELECT * FROM feature_requests ORDER BY created_at, id"
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM feature_requests WHERE status = ? ORDER BY created_at, id",
                (status,),
            ).fetchall()
        return [self._feature_request_from_row(row) for row in rows]

    def health_report(self, checked_at: str) -> HealthReport:
        sqlite_version = self.connection.execute("SELECT sqlite_version()").fetchone()[
            0
        ]
        schema_ready = (
            self.connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name IN ('tasks', 'sessions', 'task_events', 'feature_requests')"
            ).fetchone()[0]
            == 4
        )
        task_count = self.connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        session_count = self.connection.execute(
            "SELECT COUNT(*) FROM sessions"
        ).fetchone()[0]
        feature_request_count = self.connection.execute(
            "SELECT COUNT(*) FROM feature_requests"
        ).fetchone()[0]
        return HealthReport(
            ok=schema_ready,
            db_path=self.db_path,
            sqlite_version=sqlite_version,
            schema_ready=schema_ready,
            task_count=task_count,
            session_count=session_count,
            feature_request_count=feature_request_count,
            checked_at=checked_at,
        )

    def queue_stats(self) -> QueueStats:
        task_counts_by_status = self._count_rows_by("tasks", "status")
        sessions_by_stage = self._count_rows_by("sessions", "stage")
        feature_requests_by_status = self._count_rows_by("feature_requests", "status")
        feature_requests_by_kind = self._count_rows_by("feature_requests", "kind")
        open_session_count = self.connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE ended_at IS NULL OR outcome = 'in_progress'"
        ).fetchone()[0]
        token_row = self.connection.execute(
            """
            SELECT
                COALESCE(SUM(tokens_in), 0),
                COALESCE(SUM(tokens_out), 0),
                COALESCE(SUM(tokens_cache_read), 0),
                COALESCE(SUM(tokens_cache_write), 0)
            FROM sessions
            """
        ).fetchone()
        tool_call_token_row = self.connection.execute(
            """
            SELECT
                COALESCE(SUM(tool_calls_summary_tokens_in), 0),
                COALESCE(SUM(tool_calls_summary_tokens_out), 0),
                COALESCE(SUM(tool_calls_summary_cache_read), 0),
                COALESCE(SUM(tool_calls_summary_cache_write), 0)
            FROM sessions
            """
        ).fetchone()
        tool_call_summary_totals: dict[str, int] = {}
        for row in self.connection.execute(
            "SELECT tool_calls_summary FROM sessions"
        ).fetchall():
            for key, value in json.loads(row[0]).items():
                tool_call_summary_totals[key] = (
                    tool_call_summary_totals.get(key, 0) + value
                )
        return QueueStats(
            task_count_total=sum(task_counts_by_status.values()),
            task_counts_by_status=task_counts_by_status,
            session_count_total=sum(sessions_by_stage.values()),
            sessions_by_stage=sessions_by_stage,
            open_session_count=open_session_count,
            feature_request_count_total=sum(feature_requests_by_status.values()),
            feature_requests_by_status=feature_requests_by_status,
            feature_requests_by_kind=feature_requests_by_kind,
            token_totals=TokenUsage(
                tokens_in=token_row[0],
                tokens_out=token_row[1],
                tokens_cache_read=token_row[2],
                tokens_cache_write=token_row[3],
            ),
            tool_calls_summary_totals=tool_call_summary_totals,
            tool_calls_summary_token_totals=TokenUsage(
                tokens_in=tool_call_token_row[0],
                tokens_out=tool_call_token_row[1],
                tokens_cache_read=tool_call_token_row[2],
                tokens_cache_write=tool_call_token_row[3],
            ),
        )

    @staticmethod
    def _json(value: list[str]) -> str:
        return json.dumps(value)

    @staticmethod
    def _json_list(value: str | None) -> list[str]:
        if not value:
            return []
        return json.loads(value)

    def _count_rows_by(self, table: str, column: str) -> dict[str, int]:
        rows = self.connection.execute(
            f"SELECT {column}, COUNT(*) FROM {table} GROUP BY {column} ORDER BY {column}"
        ).fetchall()
        return {row[0]: row[1] for row in rows if row[0] is not None}

    def _task_from_row(self, row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            status=row["status"],
            priority=row["priority"],
            parent_id=row["parent_id"],
            depends_on=self._json_list(row["depends_on"]),
            relevant_files=self._json_list(row["relevant_files"]),
            relevant_services=self._json_list(row["relevant_services"]),
            agent_hint=row["agent_hint"],
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _session_from_row(self, row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            task_id=row["task_id"],
            stage=row["stage"],
            agent_id=row["agent_id"],
            model_name=row["model_name"],
            model_family=row["model_family"],
            model_version=row["model_version"],
            operating_mode=row["operating_mode"],
            rule_set_version=row["rule_set_version"],
            instructions_fingerprint=row["instructions_fingerprint"],
            session_ref=row["session_ref"],
            skills_used=self._json_list(row["skills_used"]),
            tool_calls_summary=json.loads(row["tool_calls_summary"]),
            tool_calls_summary_tokens=TokenUsage(
                tokens_in=row["tool_calls_summary_tokens_in"],
                tokens_out=row["tool_calls_summary_tokens_out"],
                tokens_cache_read=row["tool_calls_summary_cache_read"],
                tokens_cache_write=row["tool_calls_summary_cache_write"],
            ),
            design_patterns=self._json_list(row["design_patterns"]),
            decision_notes=row["decision_notes"],
            theory_notes=row["theory_notes"],
            tokens_in=row["tokens_in"],
            tokens_out=row["tokens_out"],
            tokens_cache_read=row["tokens_cache_read"],
            tokens_cache_write=row["tokens_cache_write"],
            outcome=row["outcome"],
            summary=row["summary"],
            notes=row["notes"],
            artifacts=self._json_list(row["artifacts"]),
            started_at=row["started_at"],
            ended_at=row["ended_at"],
        )

    @staticmethod
    def _task_event_from_row(row: sqlite3.Row) -> TaskEvent:
        return TaskEvent(
            id=row["id"],
            task_id=row["task_id"],
            from_status=row["from_status"],
            to_status=row["to_status"],
            actor=row["actor"],
            note=row["note"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _feature_request_from_row(row: sqlite3.Row) -> FeatureRequest:
        return FeatureRequest(
            id=row["id"],
            title=row["title"],
            kind=row["kind"],
            detail=row["detail"],
            status=row["status"],
            task_id=row["task_id"],
            session_id=row["session_id"],
            agent_id=row["agent_id"],
            model_name=row["model_name"],
            notes=row["notes"],
            resolution=row["resolution"],
            resolution_task_id=row["resolution_task_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
