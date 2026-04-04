# Integration Guide for Mobile and Frontend Clients

This guide explains how to integrate a mobile app with notification_ai_v2.

## 1. Base URL

Use your backend host and port 8000.

Example:

- Local machine: http://127.0.0.1:8000
- LAN device: http://192.168.x.x:8000

## 2. Primary Decision Call

Endpoint:

- POST /notifications/decide

Send each intercepted notification to this endpoint.

Sample request:

```json
{
  "notification_id": "123",
  "app_name": "WhatsApp",
  "title": "New message",
  "message": "Hey are you free?",
  "is_user_busy": 1,
  "priority_hint": 0,
  "user_preferences": {
    "force_show_apps": [],
    "force_block_apps": [],
    "allowed_time_ranges": {
      "WhatsApp": [[8, 10], [12, 14]]
    }
  }
}
```

## 3. Decision Response Format

Expected fields from /notifications/decide:

```json
{
  "decision_id": "uuid",
  "action": "SHOW",
  "recommended_delay_minutes": null,
  "scheduled_for": null,
  "engagement_level": "high",
  "interruption_score": 0.2,
  "decision_source": "gemini+pattern+context",
  "final_reason": "High engagement + low interruption risk, showing immediately"
}
```

Also includes additional metadata fields such as reason, source, confidence, category, and reason_tags.

## 4. Client Handling Rules

1. If action is SHOW:
   1. Present notification immediately.
2. If action is BLOCK:
   1. Suppress notification.
3. If action is DELAY:
   1. Do not show now.
   2. Track decision_id locally.
   3. Poll due queue endpoint.

## 5. Delayed Notification Flow

1. Poll GET /queue/due?limit=20 every few seconds.
2. For each returned item:
   1. Display to user.
   2. Call POST /queue/{decision_id}/ack.

Ack example:

- POST /queue/abc-123/ack

Response:

```json
{
  "status": "ok",
  "decision_id": "abc-123"
}
```

## 6. Feedback Flow

Send user action data for delayed notifications to improve RL and engagement learning.

Endpoint:

- POST /feedback

Request:

```json
{
  "decision_id": "abc-123",
  "user_action": "opened",
  "opened_after_seconds": 120
}
```

Notes:

- Feedback is supported for DELAY decisions.
- user_action values: opened, ignored, dismissed.

## 7. Mobile-Friendly Mapping

Server utility helper available in main.py:

- format_for_mobile_client(decision)

It returns:

```json
{
  "action": "DELAY",
  "delay": 20,
  "reason": "User is busy and engagement is medium, delaying briefly to reduce interruption"
}
```

## 8. Recommended Frontend Data Model

Keep a local map by decision_id:

1. notification payload
2. server action
3. scheduled_for
4. ack status
5. user outcome (opened/ignored/dismissed)

## 9. Reliability Tips

1. Add retry with backoff for POST /notifications/decide and /feedback.
2. Keep queue polling lightweight (5-15 second interval).
3. If backend unavailable, use safe local fallback (show important, suppress obvious spam only if high confidence).
4. Sync device clock if schedule precision is important.

## 10. Quick Validation

1. Start backend:
   1. uvicorn main:app --reload --host 0.0.0.0 --port 8000
2. Run simulation:
   1. python test_simulation.py
3. Confirm expected behavior across spam, OTP, busy promo, high-engagement promo, and low-engagement promo.
