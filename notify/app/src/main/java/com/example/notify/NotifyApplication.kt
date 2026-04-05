package com.example.notify

import android.app.Application
import com.example.notify.data.NotificationRepository
import com.example.notify.data.SettingsRepository
import com.example.notify.data.local.NotificationDatabase

class NotifyApplication : Application() {
    private val database by lazy { NotificationDatabase.getInstance(this) }

    val notificationRepository by lazy { NotificationRepository(this, database.notificationDao()) }
    val settingsRepository by lazy { SettingsRepository(this) }
}
