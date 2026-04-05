package com.example.notify.worker

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.example.notify.data.QueueApiClient
import com.example.notify.R
import com.example.notify.data.local.NotificationDatabase

class NotificationWorker(
    appContext: Context,
    params: WorkerParameters
) : CoroutineWorker(appContext, params) {
    private val queueApiClient = QueueApiClient()

    override suspend fun doWork(): Result {
        val id = inputData.getLong(KEY_ID, -1L)
        if (id <= 0L) return Result.success()

        val decisionId = inputData.getString(KEY_DECISION_ID).orEmpty()
        val appName = inputData.getString(KEY_APP_NAME).orEmpty()
        val title = inputData.getString(KEY_TITLE).orEmpty()
        val message = inputData.getString(KEY_MESSAGE).orEmpty()

        if (decisionId.isNotBlank()) {
            val dueItems = queueApiClient.fetchDueQueue()
            val isDue = dueItems.any { it.decisionId == decisionId }
            if (dueItems.isNotEmpty() && !isDue) {
                return Result.retry()
            }
        }

        showLocalNotification(applicationContext, id, appName, title, message)
        if (decisionId.isNotBlank()) {
            queueApiClient.ackDecision(decisionId)
        }
        NotificationDatabase.getInstance(applicationContext).notificationDao().deleteById(id)
        return Result.success()
    }

    companion object {
        const val KEY_ID = "notification_id"
        const val KEY_DECISION_ID = "decision_id"
        const val KEY_APP_NAME = "app_name"
        const val KEY_TITLE = "title"
        const val KEY_MESSAGE = "message"

        private const val CHANNEL_ID = "captured_notifications"
        private const val CHANNEL_NAME = "Captured Notifications"

        fun showLocalNotification(
            context: Context,
            notificationId: Long,
            appName: String,
            title: String,
            message: String
        ) {
            ensureChannel(context)

            val safeTitle = when {
                title.isNotBlank() -> title
                appName.isNotBlank() -> appName
                else -> "Notification"
            }
            val safeMessage = if (message.isNotBlank()) message else "No message"

            val notification = NotificationCompat.Builder(context, CHANNEL_ID)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle(safeTitle)
                .setContentText(safeMessage)
                .setStyle(NotificationCompat.BigTextStyle().bigText(safeMessage))
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                .setAutoCancel(true)
                .build()

            NotificationManagerCompat.from(context).notify(notificationId.toInt(), notification)
        }

        private fun ensureChannel(context: Context) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
            val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val channel = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_DEFAULT
            )
            manager.createNotificationChannel(channel)
        }
    }
}
