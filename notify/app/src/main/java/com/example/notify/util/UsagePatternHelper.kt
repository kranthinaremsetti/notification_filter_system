package com.example.notify.util

import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import java.util.Calendar

object UsagePatternHelper {
    fun topHourlyRangesForPackage(
        context: Context,
        packageName: String,
        maxRanges: Int = 2
    ): List<List<Int>> {
        if (packageName.isBlank()) return emptyList()
        if (!UsageAccessHelper.hasUsageAccess(context)) return emptyList()

        val usageStatsManager = context.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        val endTime = System.currentTimeMillis()
        val startTime = endTime - 7L * 24 * 60 * 60 * 1000

        val events = usageStatsManager.queryEvents(startTime, endTime)
        val hourlyOpenCount = IntArray(24)
        val event = UsageEvents.Event()
        val calendar = Calendar.getInstance()

        while (events.hasNextEvent()) {
            events.getNextEvent(event)
            if (event.packageName != packageName) continue
            if (event.eventType != UsageEvents.Event.ACTIVITY_RESUMED &&
                event.eventType != UsageEvents.Event.MOVE_TO_FOREGROUND
            ) continue

            calendar.timeInMillis = event.timeStamp
            val hour = calendar.get(Calendar.HOUR_OF_DAY)
            hourlyOpenCount[hour] = hourlyOpenCount[hour] + 1
        }

        return hourlyOpenCount
            .mapIndexed { hour, count -> hour to count }
            .filter { it.second > 0 }
            .sortedByDescending { it.second }
            .take(maxRanges)
            .map { (hour, _) -> listOf(hour, (hour + 1) % 24) }
    }
}
