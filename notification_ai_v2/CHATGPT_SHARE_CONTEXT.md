# Notification AI v2 - Full Share Context for ChatGPT

This file explains the full notification_ai_v2 folder so another AI assistant can understand the project quickly without reading all source files.

## 1) What this folder is

notification_ai_v2 is a standalone FastAPI backend that decides how each incoming notification should be handled:

- SHOW now
- DELAY and schedule for later
- BLOCK as spam/risky

It uses:

- Gemini as primary decision engine
- Deterministic fallback rules if Gemini is unavailable
- A reinforcement-style policy to learn better delay durations from feedback
- Calendar-aware rescheduling to avoid busy windows
- SQLite for persistence

This is intentionally separate from the older notification_ai folder.

## 2) Folder contents

- main.py
  - FastAPI app and all endpoints
  - End-to-end orchestration of decision flow
- gemini_service.py
  - Gemini prompt + API call + parse
  - Model failover chain
  - Deterministic fallback policy
- rl_policy.py
  - State key generation
  - Delay recommendation from q-values
  - Feedback-based q-value update
- storage.py
  - SQLite schema and all DB operations
- calendar_utils.py
  - UTC normalization and calendar conflict shifting
- schemas.py
  - Pydantic request/response models
- config.py
  - Env config loading (.env supported)
- requirements.txt
  - Backend python dependencies
- .env.example
  - Required env variables template
- data/notification_ai_v2.db
  - Runtime SQLite database file
- README.md
  - Setup + endpoint summary

## 3) Runtime flow (high level)

1. Client posts notification to POST /notifications/decide.
2. Backend normalizes timestamps and builds context (busy status, calendar window).
3. Backend calls GeminiDecisionEngine.decide(...).
4. If Gemini succeeds, it returns structured action/reason/confidence.
5. If Gemini fails, fallback rules return a safe deterministic decision.
6. Important-content protection is applied: if action is BLOCK but content is critical, convert to SHOW.
7. If action is DELAY:
   - RL policy chooses delay option (5..90 min buckets)
   - Scheduled time is shifted past busy calendar events
8. Decision is stored in SQLite.
9. Client polls GET /queue/due to fetch notifications that are now ready.
10. Client dispatches notification and calls POST /queue/{decision_id}/ack.
11. Client reports behavior to POST /feedback for RL learning.

## 4) API endpoints

### GET /health

Returns service status.

Response:

{
  "status": "ok",
  "service": "notification_ai_v2"
}

### POST /calendar/events

Creates or updates a busy event.

Body:

{
  "event_id": "optional-string",
  "title": "Deep Work",
  "start_at": "2026-04-04T09:00:00Z",
  "end_at": "2026-04-04T09:30:00Z"
}

Validation: end_at must be after start_at.

### GET /calendar/events?from_at=...&to_at=...

Lists events overlapping the window.

### POST /notifications/decide

Main decision endpoint.

Body (important fields):

{
  "notification_id": "client-unique-id",
  "app_name": "Instagram",
  "title": "Flash Sale",
  "message": "Mega discount offer with cashback today",
  "sender": "optional",
  "received_at": "optional-iso-datetime",
  "day_of_week": 0,
  "hour_of_day": 12,
  "metadata": {}
}

Notes:

- received_at/day_of_week/hour_of_day are optional; backend derives defaults when missing.

Response:

{
  "decision_id": "uuid",
  "action": "SHOW|DELAY|BLOCK",
  "reason": "string",
  "source": "gemini|fallback",
  "confidence": 0.0,
  "recommended_delay_minutes": 20,
  "scheduled_for": "2026-04-04T10:31:00Z",
  "category": "promotional",
  "reason_tags": ["ad", "busy"],
  "model_version": "v2"
}

### GET /queue/due?limit=20

Returns delayed decisions with scheduled_for <= now.

Important behavior:

- Records returned by this endpoint are transitioned from status=scheduled to status=ready.

### POST /queue/{decision_id}/ack

Marks a ready item as dispatched.

### POST /feedback

Updates RL q-values for a delayed decision.

Body:

{
  "decision_id": "uuid",
  "user_action": "opened|ignored|dismissed",
  "opened_after_seconds": 120
}

Rule: feedback update is allowed only for DELAY decisions with valid state_key and delay_option_minutes.

## 5) Decision logic details

### 5.1 Primary decision source: Gemini

gemini_service.py prompts Gemini to return strict JSON with:

- action
- reason
- confidence
- suggested_delay_minutes
- category
- reason_tags

Allowed actions are forced to SHOW/DELAY/BLOCK only.

### 5.2 Gemini model failover

If configured model is invalid (404), engine tries fallback models in this order:

1. model from GEMINI_MODEL
2. gemini-2.5-flash
3. gemini-2.0-flash
4. gemini-1.5-flash-latest

If all fail, system falls back to deterministic rules.

### 5.3 Deterministic fallback policy

Token groups:

- spam: "win cash", "click now", "free money", "lottery", "urgent action"
- important: "otp", "verification code", "bank", "payment", "security alert", "transaction"
- ad: "offer", "sale", "discount", "deal", "promo", "coupon", "cashback"

Order:

1. spam and not important => BLOCK
2. important => SHOW
3. ad => DELAY
4. busy => DELAY
5. else => SHOW

### 5.4 Additional safety protections in main.py

- Empty title and message => SHOW with fallback reason "Insufficient content for risk analysis".
- If action BLOCK but message is important, override to SHOW.

Important tokens used for override in main.py:

- otp
- verification code
- bank
- security alert
- transaction
- payment

## 6) Delay and scheduling logic

### 6.1 RL state key (rl_policy.py)

State key format:

app|hour_bucket|weekday/weekend|busy/free

Examples:

- instagram|h09|weekday|busy
- sms|h18|weekend|free

### 6.2 Delay options

Allowed delay buckets are:

5, 10, 15, 20, 30, 45, 60, 90 minutes

If no q-values exist for state, base delay is snapped to nearest option.

If q-values exist, highest q-value is selected (tie broken by nearest to base delay).

### 6.3 Reward update

Rewards in rl_policy.py:

- opened <= 300s: +1.2
- opened <= 1800s: +0.8
- opened > 1800s: +0.4
- opened with missing time: +0.6
- ignored: -0.5
- dismissed: -0.9
- unknown action: -0.2

Q update uses incremental mean:

new_q = old_q + (reward - old_q) / new_count

### 6.4 Calendar-aware shift

After delay is chosen, candidate delivery time is shifted to avoid busy events.

If candidate time falls inside an event [start, end), delivery is moved to end + 1 minute.

This repeats until the time is outside all overlapping events.

## 7) Database design (storage.py)

Tables:

- calendar_events
  - event_id, title, start_at, end_at, created_at, updated_at
- decisions
  - decision_id, notification_id, app_name, title, message,
    action, reason, source, confidence, category, reason_tags,
    state_key, delay_option_minutes, scheduled_for, status,
    model_version, gemini_raw, created_at
- feedback
  - decision_id, user_action, opened_after_seconds, reward, created_at
- rl_state
  - state_key, delay_option_minutes, q_value, count, updated_at

Decision status lifecycle:

- final: immediate SHOW/BLOCK
- scheduled: delayed and waiting
- ready: returned by /queue/due and awaiting dispatch
- dispatched: acked by client

## 8) Configuration

Environment variables (config.py):

- GEMINI_API_KEY
- GEMINI_MODEL (default gemini-2.5-flash)
- GEMINI_API_URL (default Google Generative Language API models endpoint)
- NOTIF_DB_PATH (default ./data/notification_ai_v2.db)
- DEFAULT_DELAY_MINUTES (default 15)
- LLM_TIMEOUT_SECONDS (default 15)

dotenv loading is optional. If python-dotenv exists, .env is auto-loaded.

## 9) Dependencies

requirements.txt:

- fastapi
- uvicorn
- httpx
- pydantic
- python-dotenv

## 10) Known operational behavior from latest validation

Validated scenarios:

- OTP/bank notification -> SHOW (gemini)
- Promotional notification while busy -> DELAY with scheduling past busy window
- Obvious spam text -> BLOCK (gemini or fallback)
- Empty payload -> SHOW fallback safeguard
- Feedback endpoint updates RL q-value
- Later similar promo keeps DELAY and uses learned policy bucket
- Queue endpoint returns due delayed items

## 11) Minimal run instructions

1. cd notification_ai_v2
2. pip install -r requirements.txt
3. copy .env.example .env
4. set GEMINI_API_KEY in .env
5. uvicorn main:app --reload --host 0.0.0.0 --port 8010

## 12) Suggested prompt when sharing to ChatGPT

Use this prompt:

"Read CHATGPT_SHARE_CONTEXT.md and help me improve notification_ai_v2 without changing public API contracts unless necessary. Prioritize spam/important classification safety, RL delay quality, and robust mobile integration assumptions. Propose code patches file-by-file."
