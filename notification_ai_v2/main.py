from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import Literal
import uuid

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from calendar_utils import ensure_utc, now_utc, shift_past_unavailable
from config import load_settings
from gemini_service import GeminiDecisionEngine
from rl_policy import ReinforcementDelayPolicy
from schemas import (
    CalendarEventIn,
    CalendarEventOut,
    DecisionOut,
    DueQueueItem,
    FeedbackIn,
    FeedbackOut,
    HealthOut,
    NotificationIn,
)
from storage import Storage
from user_pattern import UserPatternEngine


settings = load_settings()
storage = Storage(settings.database_path)
policy = ReinforcementDelayPolicy(storage=storage)
llm_engine = GeminiDecisionEngine(settings=settings)
pattern_engine = UserPatternEngine(storage=storage)

app = FastAPI(title="Context Aware Notification Backend v2", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


IMPORTANT_TOKENS = {
    "otp",
    "verification code",
    "bank",
    "security alert",
    "transaction",
    "payment",
}

IMPORTANT_TAG_HINTS = {
    "important",
    "otp",
    "bank",
    "banking",
    "security",
    "transaction",
    "payment",
}

SPAM_TAG_HINTS = {
    "spam",
    "phishing",
    "scam",
}

PROMO_TAG_HINTS = {
    "ad",
    "promo",
    "promotional",
    "sale",
    "discount",
    "offer",
    "coupon",
    "cashback",
}


def _reason_tags(raw: list[str] | None) -> list[str]:
    if not raw:
        return []
    return [tag.strip().lower() for tag in raw if tag and tag.strip()]


def _is_important_text(title: str, message: str, priority_hint: int) -> bool:
    if priority_hint == 1:
        return True

    text = f"{title} {message}".lower()
    return any(token in text for token in IMPORTANT_TOKENS)


def _normalize_app_key(app_name: str) -> str:
    app_key = (app_name or "Unknown").strip().lower()
    return app_key or "unknown"


def _app_in_list(app_name: str, values: list[str]) -> bool:
    target = _normalize_app_key(app_name)
    normalized = {_normalize_app_key(value) for value in values}
    return target in normalized


def _is_hour_allowed_for_app(app_name: str, hour: int, allowed_time_ranges: dict[str, list[list[int]]]) -> bool:
    app_key = _normalize_app_key(app_name)

    matched_ranges: list[list[int]] | None = None
    for key, ranges in allowed_time_ranges.items():
        if _normalize_app_key(key) == app_key:
            matched_ranges = ranges
            break

    if not matched_ranges:
        return True

    for window in matched_ranges:
        if len(window) < 2:
            continue
        start, end = int(window[0]), int(window[1])
        if start < 0 or start > 23 or end < 0 or end > 23:
            continue

        if start <= end and start <= hour <= end:
            return True

        # Overnight range support: [22, 3]
        if start > end and (hour >= start or hour <= end):
            return True

    return False


def _llm_signals(llm_decision: dict[str, str | float | int | list[str] | None]) -> tuple[bool, bool]:
    action = str(llm_decision.get("action", "SHOW")).upper()
    category = str(llm_decision.get("category", "")).lower()
    raw_tags = llm_decision.get("reason_tags") or []
    if not isinstance(raw_tags, list):
        raw_tags = []
    tags = {str(tag).strip().lower() for tag in raw_tags if str(tag).strip()}

    is_spam = (
        action == "BLOCK"
        or "spam" in category
        or "phishing" in category
        or bool(tags & SPAM_TAG_HINTS)
    )

    is_important = (
        "important" in category
        or "security" in category
        or "otp" in category
        or "bank" in category
        or bool(tags & IMPORTANT_TAG_HINTS)
    )

    return is_spam, is_important


def _notification_type(
    category: str,
    reason_tags: list[str],
    llm_spam: bool,
    llm_important: bool,
) -> Literal["spam", "important", "promotional", "normal"]:
    cat = (category or "").strip().lower()
    tags = {tag.strip().lower() for tag in reason_tags if tag and tag.strip()}

    if llm_spam:
        return "spam"

    if llm_important:
        return "important"

    if (
        "promo" in cat
        or "ad" in cat
        or "offer" in cat
        or "discount" in cat
        or bool(tags & PROMO_TAG_HINTS)
    ):
        return "promotional"

    return "normal"


def _interruption_score(
    is_user_busy: bool,
    engagement_level: Literal["high", "medium", "low"],
    notification_type: Literal["spam", "important", "promotional", "normal"],
) -> float:
    score = 0.45 if is_user_busy else 0.15

    if engagement_level == "high":
        score -= 0.25
    elif engagement_level == "medium":
        score += 0.05
    else:
        score += 0.30

    if notification_type == "important":
        score -= 0.15
    elif notification_type == "promotional":
        score += 0.25
    elif notification_type == "spam":
        score += 0.35
    else:
        score += 0.05

    return round(max(0.0, min(1.0, score)), 3)


def format_for_mobile_client(decision: DecisionOut) -> dict[str, str | int | None]:
    return {
        "action": decision.action,
        "delay": decision.recommended_delay_minutes,
        "reason": decision.final_reason,
    }


def _normalize_notification(notification: NotificationIn) -> tuple[datetime, int, int]:
    received_at = ensure_utc(notification.received_at or now_utc())
    hour = notification.hour_of_day if notification.hour_of_day is not None else received_at.hour
    day = notification.day_of_week if notification.day_of_week is not None else received_at.weekday()
    return received_at, int(hour), int(day)


def _calendar_events_window(start_at: datetime, end_at: datetime) -> list[tuple[datetime, datetime]]:
    rows = storage.list_calendar_events(from_at=start_at, to_at=end_at)
    events: list[tuple[datetime, datetime]] = []
    for row in rows:
        events.append((datetime.fromisoformat(row["start_at"]), datetime.fromisoformat(row["end_at"])))
    return events


def _is_user_busy(received_at: datetime, explicit_busy: int, events: list[tuple[datetime, datetime]]) -> bool:
    if explicit_busy == 1:
        return True
    for start_at, end_at in events:
        if ensure_utc(start_at) <= received_at < ensure_utc(end_at):
            return True
    return False


@app.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok", service="notification_ai_v2")


@app.post("/calendar/events", response_model=CalendarEventOut)
def upsert_calendar_event(payload: CalendarEventIn) -> CalendarEventOut:
    now_at = now_utc()
    start_at = ensure_utc(payload.start_at)
    end_at = ensure_utc(payload.end_at)

    if end_at <= start_at:
        raise HTTPException(status_code=400, detail="end_at must be after start_at")

    event_id = payload.event_id or str(uuid.uuid4())
    storage.upsert_calendar_event(
        event_id=event_id,
        title=payload.title,
        start_at=start_at,
        end_at=end_at,
        now_iso=now_at.isoformat(),
    )

    return CalendarEventOut(
        event_id=event_id,
        title=payload.title,
        start_at=start_at,
        end_at=end_at,
    )


@app.get("/calendar/events", response_model=list[CalendarEventOut])
def list_calendar_events(
    from_at: datetime = Query(...),
    to_at: datetime = Query(...),
) -> list[CalendarEventOut]:
    from_dt = ensure_utc(from_at)
    to_dt = ensure_utc(to_at)
    if to_dt <= from_dt:
        raise HTTPException(status_code=400, detail="to_at must be after from_at")

    rows = storage.list_calendar_events(from_at=from_dt, to_at=to_dt)
    return [
        CalendarEventOut(
            event_id=row["event_id"],
            title=row["title"],
            start_at=datetime.fromisoformat(row["start_at"]),
            end_at=datetime.fromisoformat(row["end_at"]),
        )
        for row in rows
    ]


@app.post("/notifications/decide", response_model=DecisionOut)
def decide_notification(notification: NotificationIn) -> DecisionOut:
    received_at, hour, day = _normalize_notification(notification)
    app_name = notification.app_name
    app_key = _normalize_app_key(app_name)
    short_delay_options = [10, 15, 20]
    long_delay_options = [30, 45, 60, 90]

    calendar_events = _calendar_events_window(
        start_at=received_at - timedelta(hours=1),
        end_at=received_at + timedelta(days=2),
    )
    busy = _is_user_busy(received_at, notification.is_user_busy, calendar_events)
    engagement_level = pattern_engine.get_engagement_level(app_key, hour)

    def _align_delay_to_profile(delay: int, profile: Literal["short", "long", "default"]) -> int:
        if profile == "short":
            if delay in short_delay_options:
                return delay
            return min(short_delay_options, key=lambda option: abs(option - delay))

        if profile == "long":
            if delay in long_delay_options:
                return delay
            return min(long_delay_options, key=lambda option: abs(option - delay))

        return delay

    def _store_and_return(
        action: str,
        reason: str,
        source: str,
        confidence: float | None,
        category: str,
        reason_tags: list[str],
        engagement_level: Literal["high", "medium", "low"] | None,
        decision_source: str,
        final_reason: str,
        suggested_delay_minutes: int | None,
        gemini_raw: dict[str, object],
        interruption_score: float,
        delay_profile: Literal["short", "long", "default"] = "default",
    ) -> DecisionOut:
        decision_id = str(uuid.uuid4())
        notification_id = notification.notification_id or decision_id
        created_at = now_utc()

        scheduled_for: datetime | None = None
        state_key: str | None = None
        delay_option: int | None = None
        status = "final"

        if action == "DELAY":
            base_delay = suggested_delay_minutes or settings.default_delay_minutes

            if delay_profile == "short":
                base_delay = min(max(int(base_delay), 10), 20)
            elif delay_profile == "long":
                base_delay = max(int(base_delay), 30)

            state_key = policy.build_state_key(
                app_name=app_name,
                when=received_at,
                is_busy=busy,
                priority_hint=notification.priority_hint,
            )
            delay_option = policy.recommend_delay(state_key=state_key, base_delay_minutes=int(base_delay))
            delay_option = _align_delay_to_profile(delay_option, delay_profile)

            candidate_delivery = received_at + timedelta(minutes=delay_option)
            scheduled_for = shift_past_unavailable(candidate_delivery, calendar_events)
            status = "scheduled"

        storage.create_decision(
            {
                "decision_id": decision_id,
                "notification_id": notification_id,
                "app_name": app_name,
                "title": notification.title,
                "message": notification.message,
                "action": action,
                "reason": reason,
                "source": source,
                "confidence": confidence,
                "category": category,
                "reason_tags": json.dumps(reason_tags),
                "state_key": state_key,
                "delay_option_minutes": delay_option,
                "scheduled_for": scheduled_for.isoformat() if scheduled_for else None,
                "status": status,
                "model_version": "v2",
                "gemini_raw": json.dumps(gemini_raw, ensure_ascii=True),
                "created_at": created_at.isoformat(),
            }
        )

        return DecisionOut(
            decision_id=decision_id,
            action=action,
            reason=reason,
            source=source,
            confidence=confidence,
            recommended_delay_minutes=delay_option,
            scheduled_for=scheduled_for,
            category=category,
            reason_tags=reason_tags,
            engagement_level=engagement_level,
            decision_source=decision_source,
            final_reason=final_reason,
            interruption_score=interruption_score,
            model_version="v2",
        )

    if not notification.message.strip() and not notification.title.strip():
        return _store_and_return(
            action="SHOW",
            reason="Insufficient content for risk analysis",
            source="fallback",
            confidence=0.3,
            category="fallback",
            reason_tags=["empty_payload"],
            engagement_level=engagement_level,
            decision_source="gemini+pattern+context",
            final_reason="Notification content is empty, so it is shown safely",
            suggested_delay_minutes=None,
            gemini_raw={"note": "empty payload safeguard"},
            interruption_score=_interruption_score(busy, engagement_level, "normal"),
        )

    payload_for_llm = {
        "notification_id": notification.notification_id,
        "app_name": notification.app_name,
        "title": notification.title,
        "message": notification.message,
        "sender": notification.sender,
        "hour_of_day": hour,
        "day_of_week": day,
        "priority_hint": notification.priority_hint,
    }
    context = {
        "is_user_busy": busy,
        "calendar_event_count": len(calendar_events),
        "default_delay_minutes": settings.default_delay_minutes,
    }

    llm_decision = llm_engine.decide(payload=payload_for_llm, context=context)
    llm_spam, llm_important = _llm_signals(llm_decision)

    source = str(llm_decision.get("source", "gemini"))
    confidence_raw = llm_decision.get("confidence")
    confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float)) else None
    category = llm_decision.get("category", "normal")
    reason_tags = _reason_tags(llm_decision.get("reason_tags"))
    gemini_reason = str(llm_decision.get("reason", "Gemini decision"))
    suggested_delay_raw = llm_decision.get("suggested_delay_minutes")
    suggested_delay = int(suggested_delay_raw) if isinstance(suggested_delay_raw, int) else None
    gemini_raw = llm_decision.get("gemini_raw", {})
    if not isinstance(gemini_raw, dict):
        gemini_raw = {"raw": str(gemini_raw)}

    is_safety_important = _is_important_text(notification.title, notification.message, notification.priority_hint)

    prefs = notification.user_preferences
    force_show_apps = prefs.force_show_apps if prefs else []
    force_block_apps = prefs.force_block_apps if prefs else []
    allowed_time_ranges = prefs.allowed_time_ranges if prefs else {}

    forced_show = _app_in_list(app_key, force_show_apps)
    forced_block = _app_in_list(app_key, force_block_apps)
    hour_allowed = _is_hour_allowed_for_app(app_key, hour, allowed_time_ranges)

    notification_type = _notification_type(str(category), reason_tags, llm_spam, llm_important)
    interruption_score = _interruption_score(busy, engagement_level, notification_type)

    if is_safety_important:
        return _store_and_return(
            action="SHOW",
            reason="Critical notification safety rule",
            source="safety",
            confidence=1.0,
            category="important",
            reason_tags=sorted(set(reason_tags + ["important_safety"])),
            engagement_level=engagement_level,
            decision_source="gemini+pattern+context",
            final_reason="Critical notification (OTP/banking/security) is always shown",
            suggested_delay_minutes=None,
            gemini_raw=gemini_raw,
            interruption_score=min(interruption_score, 0.2),
        )

    if forced_show:
        return _store_and_return(
            action="SHOW",
            reason="User preference forced immediate show",
            source="preferences",
            confidence=1.0,
            category="user_preference",
            reason_tags=sorted(set(reason_tags + ["force_show"])),
            engagement_level=engagement_level,
            decision_source="gemini+pattern+context",
            final_reason="User preference says this app should always show",
            suggested_delay_minutes=None,
            gemini_raw=gemini_raw,
            interruption_score=0.0,
        )

    if forced_block:
        return _store_and_return(
            action="BLOCK",
            reason="User preference forced block",
            source="preferences",
            confidence=1.0,
            category="user_preference",
            reason_tags=sorted(set(reason_tags + ["force_block"])),
            engagement_level=engagement_level,
            decision_source="gemini+pattern+context",
            final_reason="User preference says this app should always be blocked",
            suggested_delay_minutes=None,
            gemini_raw=gemini_raw,
            interruption_score=1.0,
        )

    if not hour_allowed:
        profile = "short" if engagement_level in {"high", "medium"} else "long"
        return _store_and_return(
            action="DELAY",
            reason="Outside user allowed delivery time",
            source="preferences",
            confidence=0.9,
            category="time_preference",
            reason_tags=sorted(set(reason_tags + ["outside_allowed_time"])),
            engagement_level=engagement_level,
            decision_source="gemini+pattern+context",
            final_reason="Current time is outside allowed delivery window, so it is delayed",
            suggested_delay_minutes=suggested_delay,
            gemini_raw=gemini_raw,
            interruption_score=max(interruption_score, 0.7),
            delay_profile=profile,
        )

    if llm_spam:
        return _store_and_return(
            action="BLOCK",
            reason=gemini_reason,
            source=source,
            confidence=confidence,
            category=str(category),
            reason_tags=sorted(set(reason_tags + ["gemini_spam"])),
            engagement_level=engagement_level,
            decision_source="gemini+pattern+context",
            final_reason="Detected spam/phishing content, so it is blocked",
            suggested_delay_minutes=None,
            gemini_raw=gemini_raw,
            interruption_score=max(interruption_score, 0.9),
        )

    if llm_important:
        return _store_and_return(
            action="SHOW",
            reason=gemini_reason,
            source=source,
            confidence=confidence,
            category=str(category),
            reason_tags=sorted(set(reason_tags + ["gemini_important"])),
            engagement_level=engagement_level,
            decision_source="gemini+pattern+context",
            final_reason="Important notification detected, so it is shown immediately",
            suggested_delay_minutes=None,
            gemini_raw=gemini_raw,
            interruption_score=min(interruption_score, 0.2),
        )

    # Final decision logic.
    if engagement_level == "low":
        if notification_type == "promotional":
            return _store_and_return(
                action="BLOCK",
                reason="Low-engagement promotional content",
                source="pattern_context",
                confidence=0.76,
                category="promotional",
                reason_tags=sorted(set(reason_tags + ["engagement_low", "promotional_low_block"])),
                engagement_level=engagement_level,
                decision_source="gemini+pattern+context",
                final_reason="Low engagement + promotional content, so blocking to avoid interruption",
                suggested_delay_minutes=None,
                gemini_raw=gemini_raw,
                interruption_score=max(interruption_score, 0.82),
            )

        return _store_and_return(
            action="DELAY",
            reason="Low engagement timing",
            source="pattern_context",
            confidence=0.72,
            category="engagement",
            reason_tags=sorted(set(reason_tags + ["engagement_low"])),
            engagement_level=engagement_level,
            decision_source="gemini+pattern+context",
            final_reason="Engagement is low, so delaying for a longer window to reduce interruption",
            suggested_delay_minutes=suggested_delay,
            gemini_raw=gemini_raw,
            interruption_score=max(interruption_score, 0.72),
            delay_profile="long",
        )

    if busy:
        if engagement_level == "high":
            return _store_and_return(
                action="SHOW",
                reason="High engagement during busy period",
                source="pattern_context",
                confidence=0.82,
                category="engagement",
                reason_tags=sorted(set(reason_tags + ["busy", "engagement_high"])),
                engagement_level=engagement_level,
                decision_source="gemini+pattern+context",
                final_reason="High engagement + low interruption risk, showing immediately",
                suggested_delay_minutes=None,
                gemini_raw=gemini_raw,
                interruption_score=min(interruption_score, 0.4),
            )

        return _store_and_return(
            action="DELAY",
            reason="User is busy and engagement is medium",
            source="pattern_context",
            confidence=0.78,
            category="engagement",
            reason_tags=sorted(set(reason_tags + ["busy", "engagement_medium"])),
            engagement_level=engagement_level,
            decision_source="gemini+pattern+context",
            final_reason="User is busy and engagement is medium, delaying briefly to reduce interruption",
            suggested_delay_minutes=suggested_delay,
            gemini_raw=gemini_raw,
            interruption_score=max(interruption_score, 0.72),
            delay_profile="short",
        )

    if engagement_level == "high":
        return _store_and_return(
            action="SHOW",
            reason="High engagement and low interruption risk",
            source="pattern_context",
            confidence=0.84,
            category="engagement",
            reason_tags=sorted(set(reason_tags + ["free", "engagement_high"])),
            engagement_level=engagement_level,
            decision_source="gemini+pattern+context",
            final_reason="High engagement + low interruption risk -> showing immediately",
            suggested_delay_minutes=None,
            gemini_raw=gemini_raw,
            interruption_score=min(interruption_score, 0.35),
        )

    if engagement_level == "medium":
        return _store_and_return(
            action="DELAY",
            reason="Medium engagement timing",
            source="pattern_context",
            confidence=0.74,
            category="engagement",
            reason_tags=sorted(set(reason_tags + ["free", "engagement_medium"])),
            engagement_level=engagement_level,
            decision_source="gemini+pattern+context",
            final_reason="Engagement is medium, so delaying briefly (10-20 min) for better timing",
            suggested_delay_minutes=suggested_delay,
            gemini_raw=gemini_raw,
            interruption_score=max(interruption_score, 0.45),
            delay_profile="short",
        )

    # Fallback for unexpected values.
    return _store_and_return(
        action="DELAY",
        reason="Conservative delay fallback",
        source="pattern_context",
        confidence=0.6,
        category="engagement",
        reason_tags=sorted(set(reason_tags + ["fallback_delay"])),
        engagement_level="medium",
        decision_source="gemini+pattern+context",
        final_reason="Fallback delay applied to avoid risky interruption",
        suggested_delay_minutes=suggested_delay,
        gemini_raw=gemini_raw,
        interruption_score=max(interruption_score, 0.6),
        delay_profile="short",
    )


@app.get("/queue/due", response_model=list[DueQueueItem])
def get_due_notifications(limit: int = Query(default=20, ge=1, le=200)) -> list[DueQueueItem]:
    rows = storage.list_due_scheduled(now_at=now_utc(), limit=limit)

    items: list[DueQueueItem] = []
    for row in rows:
        items.append(
            DueQueueItem(
                decision_id=row["decision_id"],
                notification_id=row["notification_id"],
                app_name=row["app_name"],
                title=row["title"],
                message=row["message"],
                scheduled_for=datetime.fromisoformat(row["scheduled_for"]),
                reason=row["reason"],
            )
        )

    return items


@app.post("/queue/{decision_id}/ack")
def ack_dispatched(decision_id: str) -> dict[str, str]:
    row = storage.get_decision(decision_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Decision not found")

    storage.mark_dispatched(decision_id)
    return {"status": "ok", "decision_id": decision_id}


@app.post("/feedback", response_model=FeedbackOut)
def submit_feedback(payload: FeedbackIn) -> FeedbackOut:
    decision = storage.get_decision(payload.decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")

    state_key = decision["state_key"]
    delay_option = decision["delay_option_minutes"]

    if not state_key or delay_option is None:
        raise HTTPException(
            status_code=400,
            detail="Feedback RL update is only supported for DELAY decisions",
        )

    updated_q_value, reward_milli = policy.update_from_feedback(
        state_key=state_key,
        delay_option_minutes=int(delay_option),
        user_action=payload.user_action,
        opened_after_seconds=payload.opened_after_seconds,
        now_at=now_utc(),
    )

    reward = reward_milli / 1000.0

    created_at = datetime.fromisoformat(decision["created_at"])
    app_name = decision["app_name"]
    pattern_engine.update_pattern_from_feedback(
        app_name=app_name,
        hour_of_day=ensure_utc(created_at).hour,
        user_action=payload.user_action,
        opened_after_seconds=payload.opened_after_seconds,
        now_at=now_utc(),
        reward=reward,
    )

    storage.record_feedback(
        decision_id=payload.decision_id,
        user_action=payload.user_action,
        opened_after_seconds=payload.opened_after_seconds,
        reward=reward,
        now_iso=now_utc().isoformat(),
    )

    return FeedbackOut(
        decision_id=payload.decision_id,
        reward=reward,
        updated_q_value=updated_q_value,
        delay_option_minutes=int(delay_option),
    )
