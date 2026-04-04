# Notification AI v2

## 1. Project Overview

Notification AI v2 is a FastAPI backend for intelligent notification delivery.

It separates three concerns:

1. What the notification is -> Gemini classification (spam, important, normal/promotional).
2. When to deliver -> engagement pattern + RL delay optimization.
3. Whether to interrupt now -> busy context + interruption score.

This project is standalone and separate from the older notification_ai service.

## 2. Key Features

1. Gemini classification with robust fallback rules.
2. Engagement pattern engine per app and hour bucket.
3. Context-aware decision logic for busy vs free user state.
4. RL delay optimization with short and long delay profiles.
5. User preference overrides:
   1. force_show_apps
   2. force_block_apps
   3. allowed_time_ranges
6. Interruption score in every decision response.
7. Queue workflow for delayed delivery.
8. SQLite persistence for decisions, feedback, RL state, and engagement state.

## 3. Architecture

1. API layer: main.py
2. LLM decision engine: gemini_service.py
3. Pattern engine: user_pattern.py
4. RL delay policy: rl_policy.py
5. Calendar helpers: calendar_utils.py
6. Data storage: storage.py
7. Contracts: schemas.py

High-level flow:

1. Frontend posts notification to /notifications/decide.
2. Backend classifies content and computes engagement + interruption score.
3. Backend returns SHOW/DELAY/BLOCK with human-readable reason.
4. Delayed items are fetched via /queue/due and acknowledged via /queue/{decision_id}/ack.
5. User outcomes are posted to /feedback to improve RL and pattern scoring.

## 4. API Endpoints

1. GET /health
2. POST /calendar/events
3. GET /calendar/events
4. POST /notifications/decide
5. GET /queue/due
6. POST /queue/{decision_id}/ack
7. POST /feedback

## 5. Example Request and Response

Sample request for POST /notifications/decide:

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

Sample response:

```json
{
  "action": "DELAY",
  "recommended_delay_minutes": 20,
  "engagement_level": "medium",
  "interruption_score": 0.75,
  "final_reason": "User is busy and engagement is medium, delaying to reduce interruption"
}
```

Typical full response includes:

```json
{
  "decision_id": "uuid",
  "action": "SHOW|DELAY|BLOCK",
  "recommended_delay_minutes": 20,
  "scheduled_for": "2026-04-04T10:31:00Z",
  "engagement_level": "high|medium|low",
  "interruption_score": 0.75,
  "decision_source": "gemini+pattern+context",
  "final_reason": "Human readable reasoning"
}
```

## 6. Integration Steps (Mobile App)

1. Send each incoming notification to POST /notifications/decide.
2. If action is SHOW, render immediately.
3. If action is BLOCK, drop silently.
4. If action is DELAY, hold locally and poll /queue/due.
5. When due item arrives, render it and call /queue/{decision_id}/ack.
6. Send user behavior to /feedback for learning.

For detailed frontend integration, see INTEGRATION_GUIDE.md.

## 7. Running Instructions

1. cd notification_ai_v2
2. pip install -r requirements.txt
3. copy .env.example .env
4. Set GEMINI_API_KEY in .env
5. uvicorn main:app --reload --host 0.0.0.0 --port 8010

Run demo simulation:

1. python test_simulation.py

## 8. Demo Flow

1. Start API on port 8010.
2. Run test_simulation.py.
3. Observe five cases:
   1. spam -> BLOCK
   2. OTP -> SHOW
   3. promo while busy -> DELAY
   4. promo with high engagement -> SHOW
   5. promo with low engagement -> BLOCK
