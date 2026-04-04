from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient

# Optional key for live Gemini path; fallback logic works without key too.
os.environ.setdefault("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))

from main import app  # noqa: E402


def print_case(name: str, body: dict) -> None:
    print("\n------------------------")
    print(name)
    print(f"ACTION: {body.get('action')}")
    print(f"DELAY: {body.get('recommended_delay_minutes')}")
    print(f"ENGAGEMENT LEVEL: {body.get('engagement_level')}")
    print(f"INTERRUPTION SCORE: {body.get('interruption_score')}")
    print(f"SOURCE: {body.get('decision_source')}")
    print(f"FINAL REASON: {body.get('final_reason')}")
    print("------------------------")


def make_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def main() -> None:
    client = TestClient(app)

    now = datetime.now(timezone.utc)

    # Busy window for calendar-aware delay demonstration.
    client.post(
        "/calendar/events",
        json={
            "title": "Focus Session",
            "start_at": (now + timedelta(minutes=10)).isoformat(),
            "end_at": (now + timedelta(minutes=40)).isoformat(),
        },
    )

    spam_payload = {
        "notification_id": make_id("sim-spam"),
        "app_name": "Unknown",
        "title": "Urgent prize",
        "message": "You win cash now click now and claim free money",
    }

    otp_payload = {
        "notification_id": make_id("sim-otp"),
        "app_name": "SMS",
        "title": "Bank OTP",
        "message": "Your OTP is 883211. Do not share it.",
    }

    promo_busy_payload = {
        "notification_id": make_id("sim-promo-busy"),
        "app_name": "DemoPromoBusy",
        "title": "Flash Sale",
        "message": "Mega discount offer with cashback today",
        "received_at": (now + timedelta(minutes=15)).isoformat(),
    }

    # Prime high engagement for a dedicated app/hour bucket.
    high_app = "DemoPromoHigh"
    high_seed = client.post(
        "/notifications/decide",
        json={
            "notification_id": make_id("sim-high-seed"),
            "app_name": high_app,
            "title": "Warmup promo",
            "message": "Discount offer now",
            "hour_of_day": now.hour,
        },
    ).json()

    if high_seed.get("action") == "DELAY":
        client.post(
            "/feedback",
            json={
                "decision_id": high_seed["decision_id"],
                "user_action": "opened",
                "opened_after_seconds": 30,
            },
        )

    promo_high_engagement_payload = {
        "notification_id": make_id("sim-promo-high"),
        "app_name": high_app,
        "title": "Flash Sale High",
        "message": "Big discount offer available now",
        "hour_of_day": now.hour,
    }

    # Prime low engagement for a dedicated app/hour bucket.
    low_app = "DemoPromoLow"
    low_seed = client.post(
        "/notifications/decide",
        json={
            "notification_id": make_id("sim-low-seed"),
            "app_name": low_app,
            "title": "Low warmup",
            "message": "Coupon and promo available",
            "hour_of_day": now.hour,
        },
    ).json()

    if low_seed.get("action") == "DELAY":
        client.post(
            "/feedback",
            json={
                "decision_id": low_seed["decision_id"],
                "user_action": "dismissed",
                "opened_after_seconds": None,
            },
        )

    promo_low_engagement_payload = {
        "notification_id": make_id("sim-promo-low"),
        "app_name": low_app,
        "title": "Flash Sale Low",
        "message": "Promo coupon cashback offer",
        "hour_of_day": now.hour,
        "received_at": (now + timedelta(hours=3)).isoformat(),
    }

    spam = client.post("/notifications/decide", json=spam_payload).json()
    otp = client.post("/notifications/decide", json=otp_payload).json()
    promo_busy = client.post("/notifications/decide", json=promo_busy_payload).json()
    promo_high = client.post("/notifications/decide", json=promo_high_engagement_payload).json()
    promo_low = client.post("/notifications/decide", json=promo_low_engagement_payload).json()

    print_case("SPAM NOTIFICATION", spam)
    print_case("OTP NOTIFICATION", otp)
    print_case("PROMOTIONAL (BUSY)", promo_busy)
    print_case("PROMOTIONAL (HIGH ENGAGEMENT WINDOW)", promo_high)
    print_case("PROMOTIONAL (LOW ENGAGEMENT WINDOW)", promo_low)


if __name__ == "__main__":
    main()
