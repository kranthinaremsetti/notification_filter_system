from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


DecisionAction = Literal["SHOW", "DELAY", "BLOCK"]


class UserPreferences(BaseModel):
    force_show_apps: list[str] = Field(default_factory=list)
    force_block_apps: list[str] = Field(default_factory=list)
    allowed_time_ranges: dict[str, list[list[int]]] = Field(default_factory=dict)


class NotificationIn(BaseModel):
    notification_id: str = Field(default="", description="Client-side unique id if available")
    app_name: str = Field(default="Unknown")
    title: str = Field(default="")
    message: str = Field(default="")
    sender: str = Field(default="")
    received_at: datetime | None = Field(default=None)

    day_of_week: int | None = Field(default=None, ge=0, le=6)
    hour_of_day: int | None = Field(default=None, ge=0, le=23)
    is_user_busy: int = Field(default=0, ge=0, le=1)
    priority_hint: int = Field(default=0, ge=0, le=1)

    metadata: dict[str, Any] = Field(default_factory=dict)
    user_preferences: UserPreferences | None = None


class DecisionOut(BaseModel):
    decision_id: str
    action: DecisionAction
    reason: str
    source: str
    confidence: float | None = None

    recommended_delay_minutes: int | None = None
    scheduled_for: datetime | None = None

    category: str = "normal"
    reason_tags: list[str] = Field(default_factory=list)
    engagement_level: Literal["high", "medium", "low"]
    decision_source: str = "gemini+pattern+context"
    final_reason: str = ""
    interruption_score: float
    model_version: str = "v2"


class CalendarEventIn(BaseModel):
    event_id: str | None = None
    title: str = ""
    start_at: datetime
    end_at: datetime


class CalendarEventOut(BaseModel):
    event_id: str
    title: str
    start_at: datetime
    end_at: datetime


class FeedbackIn(BaseModel):
    decision_id: str
    user_action: Literal["opened", "ignored", "dismissed"]
    opened_after_seconds: int | None = Field(default=None, ge=0)


class FeedbackOut(BaseModel):
    decision_id: str
    reward: float
    updated_q_value: float
    delay_option_minutes: int


class DueQueueItem(BaseModel):
    decision_id: str
    notification_id: str
    app_name: str
    title: str
    message: str
    scheduled_for: datetime
    reason: str


class HealthOut(BaseModel):
    status: str
    service: str
