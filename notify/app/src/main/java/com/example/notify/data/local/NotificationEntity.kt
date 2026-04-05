package com.example.notify.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "notifications")
data class NotificationEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val appName: String,
    val packageName: String,
    val title: String,
    val message: String,
    val bigText: String?,
    val timestamp: Long,
    val scheduledAt: Long? = null
)
