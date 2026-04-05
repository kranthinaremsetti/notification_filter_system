package com.example.notify.data

import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

class QueueApiClient {
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .callTimeout(25, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    fun fetchDueQueue(): List<QueueItem> {
        val request = Request.Builder()
            .url(DUE_URL)
            .get()
            .build()

        return runCatching {
            client.newCall(request).execute().use { response ->
                val body = response.body?.string().orEmpty()
                Log.d(TAG, "Queue due response: code=${response.code}, body=$body")
                if (!response.isSuccessful || body.isBlank()) return emptyList()
                parseQueueItems(body)
            }
        }.getOrElse {
            Log.e(TAG, "Failed to fetch due queue", it)
            emptyList()
        }
    }

    fun ackDecision(decisionId: String): Boolean {
        if (decisionId.isBlank()) return false
        val request = Request.Builder()
            .url("$BASE_URL/queue/$decisionId/ack")
            .post("{}".toRequestBody(JSON.toMediaType()))
            .build()

        return runCatching {
            client.newCall(request).execute().use { response ->
                val body = response.body?.string().orEmpty()
                Log.d(TAG, "Queue ack response for decisionId=$decisionId: code=${response.code}, body=$body")
                response.isSuccessful
            }
        }.getOrElse {
            Log.e(TAG, "Failed to ack decisionId=$decisionId", it)
            false
        }
    }

    private fun parseQueueItems(body: String): List<QueueItem> {
        val array = when {
            body.trimStart().startsWith("[") -> JSONArray(body)
            else -> JSONObject(body).optJSONArray("items") ?: JSONArray()
        }
        return buildList {
            for (index in 0 until array.length()) {
                val item = array.optJSONObject(index) ?: continue
                add(
                    QueueItem(
                        decisionId = item.optString("decision_id", item.optString("decisionId", "")),
                        action = item.optString("action", ""),
                        scheduledFor = item.optString("scheduled_for", item.optString("scheduledFor", "")),
                        notificationId = item.optString("notification_id", item.optString("notificationId", "")),
                        title = item.optString("title", ""),
                        message = item.optString("message", "")
                    )
                )
            }
        }
    }

    companion object {
        private const val TAG = "QueueApiClient"
        private const val BASE_URL = "https://notification-filter-system.onrender.com"
        private const val DUE_URL = "$BASE_URL/queue/due"
        private const val JSON = "application/json; charset=utf-8"
    }
}

data class QueueItem(
    val decisionId: String,
    val action: String,
    val scheduledFor: String,
    val notificationId: String,
    val title: String,
    val message: String
)
