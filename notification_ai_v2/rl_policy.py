from __future__ import annotations

from datetime import datetime
from typing import Iterable

from calendar_utils import ensure_utc
from storage import Storage


class ReinforcementDelayPolicy:
    def __init__(self, storage: Storage, delay_options: Iterable[int] | None = None):
        self.storage = storage
        self.delay_options = sorted(set(delay_options or [5, 10, 15, 20, 30, 45, 60, 90]))

    def build_state_key(
        self,
        app_name: str,
        when: datetime,
        is_busy: bool,
    ) -> str:
        dt = ensure_utc(when)
        hour_bucket = f"h{(dt.hour // 3) * 3:02d}"
        day_bucket = "weekend" if dt.weekday() >= 5 else "weekday"
        busy_bucket = "busy" if is_busy else "free"
        app_key = (app_name or "Unknown").strip().lower()
        return f"{app_key}|{hour_bucket}|{day_bucket}|{busy_bucket}"

    def recommend_delay(self, state_key: str, base_delay_minutes: int) -> int:
        rows = self.storage.get_q_values(state_key)

        if not rows:
            return self._snap_to_option(base_delay_minutes)

        # Highest q-value wins; tie-break by nearest to base delay.
        best_delay = None
        best_tuple = None

        for row in rows:
            delay = int(row["delay_option_minutes"])
            q_value = float(row["q_value"])
            tie_distance = abs(delay - base_delay_minutes)
            candidate = (q_value, -tie_distance)

            if best_tuple is None or candidate > best_tuple:
                best_tuple = candidate
                best_delay = delay

        return int(best_delay if best_delay is not None else self._snap_to_option(base_delay_minutes))

    def update_from_feedback(
        self,
        state_key: str,
        delay_option_minutes: int,
        user_action: str,
        opened_after_seconds: int | None,
        now_at: datetime,
    ) -> tuple[float, int]:
        reward = self._reward(user_action, opened_after_seconds)

        rows = self.storage.get_q_values(state_key)
        existing = {int(row["delay_option_minutes"]): row for row in rows}
        row = existing.get(delay_option_minutes)

        if row is None:
            old_q = 0.0
            old_count = 0
        else:
            old_q = float(row["q_value"])
            old_count = int(row["count"])

        # Incremental mean update.
        new_count = old_count + 1
        new_q = old_q + (reward - old_q) / new_count

        self.storage.upsert_q_value(
            state_key=state_key,
            delay_option_minutes=delay_option_minutes,
            q_value=new_q,
            count=new_count,
            updated_at=ensure_utc(now_at).isoformat(),
        )

        return new_q, int(round(reward * 1000))

    def _snap_to_option(self, delay_minutes: int) -> int:
        if delay_minutes <= self.delay_options[0]:
            return self.delay_options[0]

        return min(self.delay_options, key=lambda option: abs(option - delay_minutes))

    def _reward(self, user_action: str, opened_after_seconds: int | None) -> float:
        action = (user_action or "").strip().lower()

        if action == "opened":
            if opened_after_seconds is None:
                return 0.6
            if opened_after_seconds <= 300:
                return 1.2
            if opened_after_seconds <= 1800:
                return 0.8
            return 0.4

        if action == "ignored":
            return -0.5

        if action == "dismissed":
            return -0.9

        return -0.2
