package com.example.notify.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.notify.data.NotificationRepository
import com.example.notify.data.SettingsRepository
import com.example.notify.data.local.NotificationEntity
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class NotificationViewModel(
    private val repository: NotificationRepository,
    private val settingsRepository: SettingsRepository
) : ViewModel() {

    private val searchQuery = MutableStateFlow("")
    private val appFilter = MutableStateFlow("")
    private val autoDismissEnabled = MutableStateFlow(settingsRepository.isAutoDismissEnabled())

    val uiState: StateFlow<NotificationUiState> = combine(
        repository.getAllNotifications(),
        searchQuery,
        appFilter,
        autoDismissEnabled
    ) { allNotifications, query, filter, autoDismiss ->
        val normalizedQuery = query.trim()
        val normalizedFilter = filter.trim()

        val filtered = allNotifications.filter { notification ->
            val matchesSearch =
                normalizedQuery.isBlank() ||
                    notification.title.contains(normalizedQuery, ignoreCase = true) ||
                    notification.message.contains(normalizedQuery, ignoreCase = true) ||
                    (notification.bigText?.contains(normalizedQuery, ignoreCase = true) == true)

            val matchesFilter =
                normalizedFilter.isBlank() ||
                    notification.appName.contains(normalizedFilter, ignoreCase = true)

            matchesSearch && matchesFilter
        }

        NotificationUiState(
            notifications = filtered,
            searchQuery = query,
            appFilter = filter,
            autoDismissEnabled = autoDismiss
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = NotificationUiState(autoDismissEnabled = settingsRepository.isAutoDismissEnabled())
    )

    fun clearAll() {
        viewModelScope.launch {
            repository.clearAll()
        }
    }

    fun updateSearchQuery(query: String) {
        searchQuery.update { query }
    }

    fun updateAppFilter(filter: String) {
        appFilter.update { filter }
    }

    fun setAutoDismissEnabled(enabled: Boolean) {
        autoDismissEnabled.update { enabled }
        settingsRepository.setAutoDismissEnabled(enabled)
    }

    fun notificationById(id: Long): Flow<NotificationEntity?> = repository.getNotificationById(id)
}
