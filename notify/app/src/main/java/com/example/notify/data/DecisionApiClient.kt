package com.example.notify.data

import android.util.Log
import com.example.notify.data.local.NotificationEntity
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.time.Instant
import java.net.SocketTimeoutException
import java.time.ZoneId
import java.util.concurrent.TimeUnit

class DecisionApiClient {
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .callTimeout(25, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    fun decide(
        notificationId: Long,
        notification: NotificationEntity
    ): DecisionResult? {
        val localDateTime = Instant.ofEpochMilli(notification.timestamp)
            .atZone(ZoneId.systemDefault())
            .toLocalDateTime()

        val payload = JSONObject()
            .put("notification_id", notificationId.toString())
            .put("app_name", notification.appName)
            .put("title", notification.title)
            .put("message", if (notification.message.isNotBlank()) notification.message else notification.bigText.orEmpty())
            .put("sender", "")
            .put("received_at", Instant.ofEpochMilli(notification.timestamp).toString())
            .put("day_of_week", localDateTime.dayOfWeek.value)
            .put("hour_of_day", localDateTime.hour)
            .put("metadata", JSONObject()
                .put("additionalProp1", JSONObject())
            )

        Log.d(TAG, "Decision API request for id=$notificationId: ${payload}")

        val request = Request.Builder()
            .url(DECIDE_URL)
            .post(payload.toString().toRequestBody(JSON.toMediaType()))
            .build()

        repeat(2) { attempt ->
            try {
                client.newCall(request).execute().use { response ->
                    val body = response.body?.string().orEmpty()
                    Log.d(
                        TAG,
                        "Decision API response for id=$notificationId: code=${response.code}, body=$body"
                    )

                    if (!response.isSuccessful) return null
                    if (body.isBlank()) return null
                    val obj = JSONObject(body)
                    val result = DecisionResult(
                        decisionId = obj.optString("decision_id", ""),
                        action = obj.optString("action", "SHOW"),
                        recommendedDelayMinutes = obj.optLong("recommended_delay_minutes", -1L).takeIf { it >= 0L },
                        scheduledForEpochMs = parseScheduled(obj.optString("scheduled_for", "")),
                        interruptionScore = obj.optDouble("interruption_score", Double.NaN).takeIf { !it.isNaN() },
                        decisionSource = obj.optString("decision_source", ""),
                        finalReason = obj.optString("final_reason", "")
                    )
                    Log.d(TAG, "Decision API parsed result for id=$notificationId: $result")
                    return result
                }
            } catch (e: SocketTimeoutException) {
                Log.w(
                    TAG,
                    "Decision API timeout for id=$notificationId on attempt ${attempt + 1}/2",
                    e
                )
                if (attempt == 1) {
                    Log.e(TAG, "Decision API call failed for id=$notificationId after retry", e)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Decision API call failed for id=$notificationId", e)
                return null
            }
        }
        return null
    }

    private fun parseScheduled(value: String): Long? {
        if (value.isBlank() || value == "null") return null
        return runCatching { Instant.parse(value).toEpochMilli() }.getOrNull()
    }

    companion object {
        private const val TAG = "DecisionApiClient"
        private const val DECIDE_URL = "https://notification-filter-system.onrender.com/notifications/decide"
        private const val JSON = "application/json; charset=utf-8"
    }
}

data class DecisionResult(
    val decisionId: String,
    val action: String,
    val recommendedDelayMinutes: Long?,
    val scheduledForEpochMs: Long?,
    val interruptionScore: Double?,
    val decisionSource: String,
    val finalReason: String
)
