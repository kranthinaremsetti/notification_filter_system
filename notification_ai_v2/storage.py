from __future__ import annotations

from datetime import datetime
import os
import sqlite3
import threading
from typing import Any


class Storage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()

        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS calendar_events (
                    event_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    start_at TEXT NOT NULL,
                    end_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id TEXT PRIMARY KEY,
                    notification_id TEXT NOT NULL,
                    app_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL,
                    category TEXT NOT NULL,
                    reason_tags TEXT NOT NULL,
                    state_key TEXT,
                    delay_option_minutes INTEGER,
                    scheduled_for TEXT,
                    status TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    gemini_raw TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_decisions_scheduled
                ON decisions(status, scheduled_for);

                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_id TEXT NOT NULL,
                    user_action TEXT NOT NULL,
                    opened_after_seconds INTEGER,
                    reward REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(decision_id) REFERENCES decisions(decision_id)
                );

                CREATE TABLE IF NOT EXISTS rl_state (
                    state_key TEXT NOT NULL,
                    delay_option_minutes INTEGER NOT NULL,
                    q_value REAL NOT NULL,
                    count INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(state_key, delay_option_minutes)
                );

                CREATE TABLE IF NOT EXISTS user_pattern_engagement (
                    app_name TEXT NOT NULL,
                    hour_bucket INTEGER NOT NULL,
                    high_score REAL NOT NULL,
                    medium_score REAL NOT NULL,
                    low_score REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(app_name, hour_bucket)
                );
                """
            )

    def upsert_calendar_event(
        self,
        event_id: str,
        title: str,
        start_at: datetime,
        end_at: datetime,
        now_iso: str,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO calendar_events(event_id, title, start_at, end_at, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    title=excluded.title,
                    start_at=excluded.start_at,
                    end_at=excluded.end_at,
                    updated_at=excluded.updated_at
                """,
                (event_id, title, start_at.isoformat(), end_at.isoformat(), now_iso, now_iso),
            )

    def list_calendar_events(self, from_at: datetime, to_at: datetime) -> list[sqlite3.Row]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, title, start_at, end_at
                FROM calendar_events
                WHERE end_at >= ? AND start_at <= ?
                ORDER BY start_at ASC
                """,
                (from_at.isoformat(), to_at.isoformat()),
            ).fetchall()
            return rows

    def create_decision(self, row: dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO decisions(
                    decision_id, notification_id, app_name, title, message,
                    action, reason, source, confidence, category, reason_tags,
                    state_key, delay_option_minutes, scheduled_for, status,
                    model_version, gemini_raw, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["decision_id"],
                    row["notification_id"],
                    row["app_name"],
                    row["title"],
                    row["message"],
                    row["action"],
                    row["reason"],
                    row["source"],
                    row.get("confidence"),
                    row["category"],
                    row["reason_tags"],
                    row.get("state_key"),
                    row.get("delay_option_minutes"),
                    row.get("scheduled_for"),
                    row["status"],
                    row["model_version"],
                    row.get("gemini_raw"),
                    row["created_at"],
                ),
            )

    def get_decision(self, decision_id: str) -> sqlite3.Row | None:
        with self._lock, self._connect() as conn:
            return conn.execute(
                "SELECT * FROM decisions WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()

    def list_due_scheduled(self, now_at: datetime, limit: int) -> list[sqlite3.Row]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM decisions
                WHERE status = 'scheduled' AND scheduled_for <= ?
                ORDER BY scheduled_for ASC
                LIMIT ?
                """,
                (now_at.isoformat(), limit),
            ).fetchall()

            if rows:
                conn.executemany(
                    "UPDATE decisions SET status='ready' WHERE decision_id = ?",
                    [(row["decision_id"],) for row in rows],
                )

            return rows

    def mark_dispatched(self, decision_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE decisions SET status='dispatched' WHERE decision_id = ?",
                (decision_id,),
            )

    def record_feedback(
        self,
        decision_id: str,
        user_action: str,
        opened_after_seconds: int | None,
        reward: float,
        now_iso: str,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO feedback(decision_id, user_action, opened_after_seconds, reward, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (decision_id, user_action, opened_after_seconds, reward, now_iso),
            )

    def get_q_values(self, state_key: str) -> list[sqlite3.Row]:
        with self._lock, self._connect() as conn:
            return conn.execute(
                "SELECT * FROM rl_state WHERE state_key = ?",
                (state_key,),
            ).fetchall()

    def upsert_q_value(
        self,
        state_key: str,
        delay_option_minutes: int,
        q_value: float,
        count: int,
        updated_at: str,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rl_state(state_key, delay_option_minutes, q_value, count, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(state_key, delay_option_minutes)
                DO UPDATE SET q_value=excluded.q_value, count=excluded.count, updated_at=excluded.updated_at
                """,
                (state_key, delay_option_minutes, q_value, count, updated_at),
            )

    def get_engagement_scores(self, app_name: str, hour_bucket: int) -> sqlite3.Row | None:
        with self._lock, self._connect() as conn:
            return conn.execute(
                """
                SELECT app_name, hour_bucket, high_score, medium_score, low_score, updated_at
                FROM user_pattern_engagement
                WHERE app_name = ? AND hour_bucket = ?
                """,
                (app_name, hour_bucket),
            ).fetchone()

    def upsert_engagement_scores(
        self,
        app_name: str,
        hour_bucket: int,
        high_score: float,
        medium_score: float,
        low_score: float,
        updated_at: str,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_pattern_engagement(
                    app_name, hour_bucket, high_score, medium_score, low_score, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(app_name, hour_bucket)
                DO UPDATE SET
                    high_score=excluded.high_score,
                    medium_score=excluded.medium_score,
                    low_score=excluded.low_score,
                    updated_at=excluded.updated_at
                """,
                (app_name, hour_bucket, high_score, medium_score, low_score, updated_at),
            )
