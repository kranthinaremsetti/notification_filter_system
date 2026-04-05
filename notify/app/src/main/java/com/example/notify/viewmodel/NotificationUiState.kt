package com.example.notify.viewmodel

import com.example.notify.data.local.NotificationEntity

data class NotificationUiState(
    val notifications: List<NotificationEntity> = emptyList(),
    val searchQuery: String = "",
    val appFilter: String = "",
    val autoDismissEnabled: Boolean = true
)
