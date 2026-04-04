# Context-Aware Notification Intelligence

AI-powered notification decision system built with FastAPI, classic ML, and rule-based safety.

## What This Project Solves
Mobile notifications are noisy, distracting, and often risky (spam/scam content). This project classifies each incoming notification into:

- SHOW
- DELAY
- BLOCK

using context, app behavior, message content, and optional user personalization.

## Current Capabilities
- Context-aware notification scoring with RandomForestClassifier
- Spam detection with confidence score using TF-IDF + MultinomialNB
- Scam warning payload for blocked spam
- Advertisement detection and delayed handling
- Rule-engine overrides (meeting + SMS priority logic)
- Onboarding-ready personalization modes:
	- quick mode (default, immediate decisions)
	- training mode (collect behavior, always SHOW)
- Behavior logging and personalized model retraining API endpoints

## Decision Pipeline
```text
Incoming Notification
				|
				v
1) Spam Check (Naive Bayes + confidence)
	 - If spam: BLOCK + warning + confidence
				|
				v
2) Ad Detection (keyword-based)
	 - If ad: DELAY 120 minutes
				|
				v
3) Rule Engine
	 - Meeting + non-normal => BLOCK
	 - SMS => SHOW
				|
				v
4) ML Prediction (global or personalized model)
	 - SHOW / DELAY / BLOCK + score
```

## Project Structure
```text
notification_filter_system/
├── README.md
├── .gitignore
└── notification_ai/
		├── api.py
		├── main.py
		├── train_notification_model.py
		├── train_spam_model.py
		├── data/
		│   ├── sms_spam_collection.csv
		│   └── user_behavior_log.csv (generated at runtime)
		└── models/
				├── notification_model.pkl
				├── app_encoder.pkl
				├── type_encoder.pkl
				├── spam_model.pkl
				├── vectorizer.pkl
				└── personalized_notification_model.pkl (optional, generated)
```

## Tech Stack
- Python
- FastAPI + Pydantic
- scikit-learn
- pandas + numpy
- joblib

## Model Details

### Notification Model
- Algorithm: RandomForestClassifier
- Training script: notification_ai/train_notification_model.py
- Dataset: synthetic (5000 samples)
- Features:
	- app_name
	- hour
	- day_of_week
	- is_meeting
	- notification_type
- Typical observed accuracy: around 0.72

### Spam Model
- Algorithm: MultinomialNB
- Vectorizer: TfidfVectorizer
- Training script: notification_ai/train_spam_model.py
- Dataset file: notification_ai/data/sms_spam_collection.csv
- Latest observed run in project workflow: high accuracy (around 0.97)

## Installation
1. Clone repository.
2. Create and activate virtual environment.
3. Install dependencies:

```bash
pip install fastapi uvicorn pandas numpy scikit-learn joblib
```

## Run Locally
From the notification_ai directory:

```bash
cd notification_ai
python train_notification_model.py
python train_spam_model.py
python main.py
uvicorn api:app --reload
```

API base URL: http://127.0.0.1:8000

For Expo on a physical phone, use your PC LAN IP in the app (not localhost), for example: http://192.168.1.20:8000/predict

## API Reference

### POST /predict
Primary decision endpoint.

Request body:
```json
{
	"app": "WhatsApp",
	"hour": 14,
	"day": 1,
	"is_meeting": 0,
	"notif_type": "normal",
	"message": "Hey bro",
	"mode": "quick",
	"user_action": null
}
```

Notes:
- mode supports quick or training.
- In training mode, prediction pipeline is skipped, data is logged, and response is always SHOW.

Example responses:

ML response:
```json
{
	"action": "SHOW",
	"score": 0.83
}
```

Rule response:
```json
{
	"action": "SHOW",
	"reason": "Rule-based decision"
}
```

Ad response:
```json
{
	"action": "DELAY",
	"delay_minutes": 120,
	"reason": "Ad scheduled for later"
}
```

Spam warning response:
```json
{
	"action": "BLOCK",
	"reason": "Spam detected",
	"warning": "This message is 92% likely to be a scam",
	"confidence": 0.92
}
```

Training mode response:
```json
{
	"action": "SHOW",
	"reason": "Training mode collecting data",
	"mode": "training"
}
```

### POST /feedback
Logs explicit user behavior labels.

Request body:
```json
{
	"app": "Instagram",
	"hour": 20,
	"day": 4,
	"is_meeting": 0,
	"notif_type": "ad",
	"message": "offer offer",
	"user_action": "ignored"
}
```

Response:
```json
{
	"status": "saved",
	"user_action": "ignored"
}
```

### POST /train-personalized
Trains a personalized RandomForest model from logged behavior data.

Response (example):
```json
{
	"status": "trained",
	"samples": 120,
	"accuracy": 0.81,
	"model_path": "personalized_notification_model.pkl"
}
```

## Judge Demo Script
1. Train base models.
2. Start API.
3. Call /predict in quick mode with normal, ad, and spam messages.
4. Show spam warning confidence output.
5. Call /predict in training mode to collect behavior.
6. Submit explicit labels with /feedback.
7. Call /train-personalized and show adaptive capability.

## Practical Impact
- Reduces distracting low-priority notifications.
- Adds scam-risk awareness with confidence-driven warning.
- Combines deterministic reliability (rules) with adaptive intelligence (ML).
- Supports a cold-start strategy through quick mode and training mode.

## Current Limitations
- Notification model uses synthetic training data.
- Ad detection is keyword-based, not learned.
- Personalization quality depends on enough user behavior samples.

Built for hackathon demos: explainable, extensible, and deployment-friendly. 🚀