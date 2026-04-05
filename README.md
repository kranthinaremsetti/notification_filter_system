# Notification Filter System

Notification Filter System is an end-to-end project with:

1. A FastAPI backend that decides whether to SHOW, DELAY, or BLOCK notifications.
2. An Android app that captures system notifications, calls the backend, and displays notifications based on the decision.
3. A generated APK artifact in the repository root.

## Repository Layout

```text
notification_filter_system/
|- README.md
|- app-release-unsigned.apk
|- notification_ai_v2/
|  |- main.py
|  |- gemini_service.py
|  |- rl_policy.py
|  |- user_pattern.py
|  |- storage.py
|  |- schemas.py
|  |- config.py
|  |- test_simulation.py
|  |- requirements.txt
|  |- INTEGRATION_GUIDE.md
|  `- data/notification_ai_v2.db
`- notify/
   |- app/
   |  |- build.gradle.kts
   |  |- src/main/AndroidManifest.xml
   |  `- src/main/java/com/example/notify/...
   |- build.gradle.kts
   |- settings.gradle.kts
   |- gradle/libs.versions.toml
   `- gradlew, gradlew.bat
```

## Backend (notification_ai_v2)

### What it does

The backend takes each incoming notification and returns a decision:

1. SHOW
2. DELAY
3. BLOCK

Decisioning combines:

1. Gemini classification with strict JSON output.
2. Deterministic fallback rules if Gemini is unavailable.
3. Engagement pattern scoring per app and hour bucket.
4. RL-based delay selection across delay buckets.
5. Calendar-aware scheduling so delayed notifications avoid busy events.

### Current API Endpoints

1. GET /health
2. POST /calendar/events
3. GET /calendar/events
4. POST /notifications/decide
5. GET /queue/due
6. POST /queue/{decision_id}/ack
7. POST /feedback

### Sample decide request

```json
{
  "notification_id": "123",
  "app_name": "WhatsApp",
  "title": "New message",
  "message": "Hey are you free?"
}
```

### Backend configuration

Configured via environment variables in notification_ai_v2/config.py:

1. GEMINI_API_KEY
2. GEMINI_MODEL (default: gemini-2.5-flash)
3. GEMINI_API_URL
4. NOTIF_DB_PATH (default: ./data/notification_ai_v2.db)
5. DEFAULT_DELAY_MINUTES (default: 15)
6. LLM_TIMEOUT_SECONDS (default: 15)

Note: dotenv loading is optional. If python-dotenv is installed, a .env file will be loaded automatically.

### Run backend locally

```bash
cd notification_ai_v2
pip install -r requirements.txt
set GEMINI_API_KEY=your_key_here
uvicorn main:app --reload --host 0.0.0.0 --port 8010
```

Local API URL: http://127.0.0.1:8010

## Android App (notify)

### What it does

The app captures incoming Android notifications using NotificationListenerService, sends them to backend, and applies model decisions:

1. BLOCK: delete from local inbox and do not show.
2. SHOW: display immediately.
3. DELAY: schedule local WorkManager task and wait for due queue confirmation before displaying.

### Key app components

1. Notification capture service:
   notify/app/src/main/java/com/example/notify/service/NotificationCaptureService.kt
2. Backend decision client:
   notify/app/src/main/java/com/example/notify/data/DecisionApiClient.kt
3. Queue polling and ack client:
   notify/app/src/main/java/com/example/notify/data/QueueApiClient.kt
4. Processing pipeline and scheduling:
   notify/app/src/main/java/com/example/notify/data/NotificationRepository.kt
5. Delayed notification worker:
   notify/app/src/main/java/com/example/notify/worker/NotificationWorker.kt
6. Local persistence (Room DB):
   notify/app/src/main/java/com/example/notify/data/local/NotificationDatabase.kt

### Android permissions used

Defined in notify/app/src/main/AndroidManifest.xml:

1. android.permission.READ_CALENDAR
2. android.permission.POST_NOTIFICATIONS
3. android.permission.INTERNET
4. android.permission.PACKAGE_USAGE_STATS
5. Notification listener service bind permission

### Backend URL used by app

The app currently points to deployed backend URLs in code:

1. https://notification-filter-system.onrender.com/notifications/decide
2. https://notification-filter-system.onrender.com/queue/due
3. https://notification-filter-system.onrender.com/queue/{decision_id}/ack

These are defined in:

1. notify/app/src/main/java/com/example/notify/data/DecisionApiClient.kt
2. notify/app/src/main/java/com/example/notify/data/QueueApiClient.kt

If you want to test with local backend, update these constants to your machine IP and port 8010.

### Run Android app

Using Android Studio:

1. Open the notify folder as project.
2. Sync Gradle.
3. Build and run on device/emulator (minSdk 24, targetSdk 36).
4. Grant required permissions in app and system settings.

Using command line (Windows PowerShell):

```bash
cd notify
./gradlew.bat assembleDebug
```

APK output is generated under notify/app/build/outputs/apk/.

## End-to-End Flow

1. Notification is posted on Android device.
2. NotificationCaptureService captures and stores it in Room.
3. App calls POST /notifications/decide.
4. Backend returns SHOW/DELAY/BLOCK with metadata.
5. App executes action:
   1. SHOW now, or
   2. BLOCK and remove, or
   3. DELAY using WorkManager.
6. For delayed notifications, worker polls GET /queue/due and then calls POST /queue/{decision_id}/ack after showing.
7. Optional feedback can be sent to POST /feedback for RL updates.

## APK Artifact in Root

The root file app-release-unsigned.apk is a build artifact.

Notes:

1. Unsigned APK cannot be installed on most devices until signed.
2. Keep keystore files and signing secrets out of git.
3. For distribution, prefer GitHub Releases assets instead of committing large APK files repeatedly.

## Quick Troubleshooting

1. If app is not receiving notifications:
   1. Enable Notification Access for the app in system settings.
2. If queue delivery is not happening:
   1. Verify backend URL constants in DecisionApiClient.kt and QueueApiClient.kt.
3. If backend falls back too often:
   1. Check GEMINI_API_KEY and network access from backend host.
4. If calendar-aware behavior seems wrong:
   1. Verify READ_CALENDAR permission is granted.