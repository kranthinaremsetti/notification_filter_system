from __future__ import annotations

from datetime import datetime
from typing import Literal

from calendar_utils import ensure_utc
from storage import Storage


EngagementLevel = Literal["high", "medium", "low"]


class UserPatternEngine:
    def __init__(self, storage: Storage):
        self.storage = storage

    def get_engagement_level(self, app_name: str, hour_of_day: int) -> EngagementLevel:
        app_key = self._normalize_app(app_name)
        hour = self._normalize_hour(hour_of_day)
        scores = self._get_scores(app_key, hour)

        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if not ordered:
            return "medium"

        # Default bootstrap gives medium the highest score for unknown states.
        return ordered[0][0]  # type: ignore[return-value]

    def update_pattern_from_feedback(
        self,
        app_name: str,
        hour_of_day: int,
        user_action: str,
        opened_after_seconds: int | None,
        now_at: datetime,
        reward: float | None = None,
    ) -> EngagementLevel:
        app_key = self._normalize_app(app_name)
        hour = self._normalize_hour(hour_of_day)
        scores = self._get_scores(app_key, hour)

        # Gentle decay keeps older behavior from dominating forever.
        scores["high"] *= 0.97
        scores["medium"] *= 0.97
        scores["low"] *= 0.97

        bucket = self._feedback_bucket(user_action, opened_after_seconds)
        scores[bucket] += 1.0

        # RL reward reinforces the same pattern estimate.
        if reward is not None:
            reward_weight = min(abs(reward), 2.0) * 0.25
            if reward >= 0:
                scores[bucket] += reward_weight
            else:
                scores["low"] += reward_weight

        self.storage.upsert_engagement_scores(
            app_name=app_key,
            hour_bucket=hour,
            high_score=max(scores["high"], 0.0),
            medium_score=max(scores["medium"], 0.0),
            low_score=max(scores["low"], 0.0),
            updated_at=ensure_utc(now_at).isoformat(),
        )

        return self.get_engagement_level(app_key, hour)

    def _feedback_bucket(self, user_action: str, opened_after_seconds: int | None) -> EngagementLevel:
        action = (user_action or "").strip().lower()

        if action == "opened":
            if opened_after_seconds is not None and opened_after_seconds <= 300:
                return "high"
            return "medium"

        if action in {"ignored", "dismissed"}:
            return "low"

        return "medium"

    def _get_scores(self, app_name: str, hour_of_day: int) -> dict[str, float]:
        row = self.storage.get_engagement_scores(app_name=app_name, hour_bucket=hour_of_day)
        if row is None:
            return {"high": 0.0, "medium": 1.0, "low": 0.0}

        return {
            "high": float(row["high_score"]),
            "medium": float(row["medium_score"]),
            "low": float(row["low_score"]),
        }

    def _normalize_app(self, app_name: str) -> str:
        value = (app_name or "Unknown").strip().lower()
        return value or "unknown"

    def _normalize_hour(self, hour_of_day: int) -> int:
        if hour_of_day < 0:
            return 0
        if hour_of_day > 23:
            return 23
        return int(hour_of_day)
