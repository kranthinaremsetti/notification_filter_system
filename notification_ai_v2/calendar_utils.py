from __future__ import annotations

from datetime import datetime, timedelta, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def shift_past_unavailable(
    candidate_time: datetime,
    events: list[tuple[datetime, datetime]],
) -> datetime:
    """If candidate_time falls inside an unavailable event, move it to event end."""
    adjusted = ensure_utc(candidate_time)
    changed = True

    # Repeat because moving to one event's end might still be inside another event.
    while changed:
        changed = False
        for start_at, end_at in events:
            start_at = ensure_utc(start_at)
            end_at = ensure_utc(end_at)
            if start_at <= adjusted < end_at:
                adjusted = end_at + timedelta(minutes=1)
                changed = True
                break

    return adjusted
