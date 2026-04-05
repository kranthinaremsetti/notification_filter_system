package com.example.notify.data

import android.content.Context
import android.util.Log
import com.example.notify.data.local.NotificationDao
import com.example.notify.data.local.NotificationEntity
import com.example.notify.util.CalendarHelper
import com.example.notify.worker.NotificationWorker
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext
import androidx.work.Data
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager

class NotificationRepository(
    private val appContext: Context,
    private val notificationDao: NotificationDao
) {
    private val decisionApiClient = DecisionApiClient()

    fun getAllNotifications(): Flow<List<NotificationEntity>> = notificationDao.getAllNotifications()

    fun getNotificationById(id: Long): Flow<NotificationEntity?> = notificationDao.getNotificationById(id)

    suspend fun processCapturedNotification(notification: NotificationEntity) = withContext(Dispatchers.IO) {
        val now = System.currentTimeMillis()
        val busyUntilNow = CalendarHelper.isUserBusy(appContext, now)
        val isBusy = busyUntilNow != null && busyUntilNow > now

        val storedNotification = notification.copy(scheduledAt = null)
        val id = notificationDao.insertNotification(storedNotification)
        if (id <= 0L) return@withContext

        val modelDecision = decisionApiClient.decide(
            notificationId = id,
            notification = storedNotification
        )

        val action = modelDecision?.action?.uppercase().orEmpty()

        if (action == "BLOCK") {
            notificationDao.deleteById(id)
            Log.d(TAG, "Decision id=$id action=BLOCK -> deleted from Room")
            return@withContext
        }

        if (action == "SHOW") {
            NotificationWorker.showLocalNotification(
                context = appContext,
                notificationId = id,
                appName = storedNotification.appName,
                title = storedNotification.title,
                message = if (storedNotification.message.isNotBlank()) {
                    storedNotification.message
                } else {
                    storedNotification.bigText.orEmpty()
                }
            )
            notificationDao.deleteById(id)
            Log.d(TAG, "Decision id=$id action=SHOW -> shown immediately (calendar ignored)")
            return@withContext
        }

        val apiScheduledAt = when {
            modelDecision?.scheduledForEpochMs != null -> modelDecision.scheduledForEpochMs
            modelDecision?.recommendedDelayMinutes != null -> {
                now + modelDecision.recommendedDelayMinutes * 60_000L
            }
            else -> null
        }

        val sendAt = when {
            apiScheduledAt != null -> {
                val calendarBlockEnd = CalendarHelper.eventEndIfBusyAt(appContext, apiScheduledAt)
                val adjusted = if (calendarBlockEnd != null && calendarBlockEnd > apiScheduledAt) {
                    calendarBlockEnd
                } else {
                    apiScheduledAt
                }
                adjusted.takeIf { it > now }
            }
            isBusy -> busyUntilNow?.takeIf { it > now }
            else -> null
        }

        Log.d(
            TAG,
            "Decision id=$id package=${storedNotification.packageName} action=${if (action.isBlank()) "FALLBACK" else action} isBusy=$isBusy sendAt=${sendAt ?: "IMMEDIATE"}"
        )

        if (sendAt == null) {
            NotificationWorker.showLocalNotification(
                context = appContext,
                notificationId = id,
                appName = storedNotification.appName,
                title = storedNotification.title,
                message = if (storedNotification.message.isNotBlank()) {
                    storedNotification.message
                } else {
                    storedNotification.bigText.orEmpty()
                }
            )
            notificationDao.deleteById(id)
            return@withContext
        }

        notificationDao.updateScheduledAt(id, sendAt)

        val delayMs = (sendAt - now).coerceAtLeast(0L)
        val inputData = Data.Builder()
            .putLong(NotificationWorker.KEY_ID, id)
            .putString(NotificationWorker.KEY_DECISION_ID, modelDecision?.decisionId.orEmpty())
            .putString(NotificationWorker.KEY_APP_NAME, storedNotification.appName)
            .putString(NotificationWorker.KEY_TITLE, storedNotification.title)
            .putString(
                NotificationWorker.KEY_MESSAGE,
                if (storedNotification.message.isNotBlank()) {
                    storedNotification.message
                } else {
                    storedNotification.bigText.orEmpty()
                }
            )
            .build()

        val work = OneTimeWorkRequestBuilder<NotificationWorker>()
            .setInitialDelay(delayMs, TimeUnit.MILLISECONDS)
            .setInputData(inputData)
            .build()

        WorkManager.getInstance(appContext).enqueueUniqueWork(
            "captured_notification_$id",
            androidx.work.ExistingWorkPolicy.REPLACE,
            work
        )
    }

    suspend fun clearAll() {
        notificationDao.clearAll()
    }

    companion object {
        private const val TAG = "NotificationRepository"
    }
}
