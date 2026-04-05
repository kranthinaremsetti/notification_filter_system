package com.example.notify.util

import android.content.Context
import android.provider.CalendarContract

object CalendarHelper {
    fun isUserBusy(context: Context, currentTime: Long): Long? {
        return eventEndIfBusyAt(context, currentTime)
    }

    fun eventEndIfBusyAt(context: Context, targetTime: Long): Long? {
        val projection = arrayOf(
            CalendarContract.Events.DTSTART,
            CalendarContract.Events.DTEND
        )
        val selection = "${CalendarContract.Events.DTSTART} <= ? AND ${CalendarContract.Events.DTEND} >= ?"
        val args = arrayOf(targetTime.toString(), targetTime.toString())

        return runCatching {
            context.contentResolver.query(
                CalendarContract.Events.CONTENT_URI,
                projection,
                selection,
                args,
                CalendarContract.Events.DTEND + " ASC"
            )?.use { cursor ->
                var busyUntil: Long? = null
                val endIndex = cursor.getColumnIndex(CalendarContract.Events.DTEND)
                while (cursor.moveToNext()) {
                    val eventEnd = if (endIndex >= 0) cursor.getLong(endIndex) else 0L
                    if (eventEnd > targetTime) {
                        if (busyUntil == null || eventEnd < busyUntil) busyUntil = eventEnd
                    }
                }
                busyUntil
            }
        }.getOrNull()
    }
}
