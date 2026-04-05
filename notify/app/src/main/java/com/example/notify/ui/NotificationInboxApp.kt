package com.example.notify.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.example.notify.R
import com.example.notify.data.local.NotificationEntity
import com.example.notify.viewmodel.NotificationUiState
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.flow.Flow

private const val INBOX_ROUTE = "inbox"
private const val DETAIL_ROUTE = "detail"

@Composable
fun NotificationInboxApp(
    uiState: NotificationUiState,
    notificationAccessEnabled: Boolean,
    usageAccessEnabled: Boolean,
    onOpenNotificationAccessSettings: () -> Unit,
    onOpenUsageAccessSettings: () -> Unit,
    onClearAll: () -> Unit,
    onSearchQueryChange: (String) -> Unit,
    onFilterAppChange: (String) -> Unit,
    onAutoDismissChanged: (Boolean) -> Unit,
    detailFlowProvider: (Long) -> Flow<NotificationEntity?>
) {
    val navController = rememberNavController()

    NavHost(navController = navController, startDestination = INBOX_ROUTE) {
        composable(INBOX_ROUTE) {
            NotificationInboxScreen(
                uiState = uiState,
                notificationAccessEnabled = notificationAccessEnabled,
                usageAccessEnabled = usageAccessEnabled,
                onOpenNotificationAccessSettings = onOpenNotificationAccessSettings,
                onOpenUsageAccessSettings = onOpenUsageAccessSettings,
                onClearAll = onClearAll,
                onSearchQueryChange = onSearchQueryChange,
                onFilterAppChange = onFilterAppChange,
                onAutoDismissChanged = onAutoDismissChanged,
                onOpenDetail = { id -> navController.navigate("$DETAIL_ROUTE/$id") }
            )
        }

        composable(
            route = "$DETAIL_ROUTE/{id}",
            arguments = listOf(navArgument("id") { type = NavType.LongType })
        ) { backStackEntry ->
            val id = backStackEntry.arguments?.getLong("id") ?: return@composable
            val notification by detailFlowProvider(id).collectAsStateWithLifecycle(initialValue = null)
            NotificationDetailScreen(
                notification = notification,
                onBack = { navController.popBackStack() }
            )
        }
    }
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
private fun NotificationInboxScreen(
    uiState: NotificationUiState,
    notificationAccessEnabled: Boolean,
    usageAccessEnabled: Boolean,
    onOpenNotificationAccessSettings: () -> Unit,
    onOpenUsageAccessSettings: () -> Unit,
    onClearAll: () -> Unit,
    onSearchQueryChange: (String) -> Unit,
    onFilterAppChange: (String) -> Unit,
    onAutoDismissChanged: (Boolean) -> Unit,
    onOpenDetail: (Long) -> Unit
) {
    var showClearDialog by remember { mutableStateOf(false) }

    if (showClearDialog) {
        AlertDialog(
            onDismissRequest = { showClearDialog = false },
            confirmButton = {
                Button(onClick = {
                    onClearAll()
                    showClearDialog = false
                }) {
                    Text(text = "Confirm")
                }
            },
            dismissButton = {
                TextButton(onClick = { showClearDialog = false }) {
                    Text(text = "Cancel")
                }
            },
            title = { Text(text = "Clear all notifications") },
            text = { Text(text = "This removes all captured notifications from the app inbox.") }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(text = "Central Notification Inbox") },
                actions = {
                    TextButton(onClick = { showClearDialog = true }) {
                        Text(text = androidx.compose.ui.res.stringResource(id = R.string.clear_all))
                    }
                }
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            if (!notificationAccessEnabled) {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(
                        modifier = Modifier.padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Text(text = androidx.compose.ui.res.stringResource(id = R.string.notification_access_required))
                        Button(onClick = onOpenNotificationAccessSettings) {
                            Text(text = androidx.compose.ui.res.stringResource(id = R.string.open_settings))
                        }
                    }
                }
            }

            if (!usageAccessEnabled) {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(
                        modifier = Modifier.padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Text(text = androidx.compose.ui.res.stringResource(id = R.string.usage_access_required))
                        Button(onClick = onOpenUsageAccessSettings) {
                            Text(text = androidx.compose.ui.res.stringResource(id = R.string.open_settings))
                        }
                    }
                }
            }

            OutlinedTextField(
                value = uiState.searchQuery,
                onValueChange = onSearchQueryChange,
                modifier = Modifier.fillMaxWidth(),
                label = { Text(text = androidx.compose.ui.res.stringResource(id = R.string.search_hint)) },
                singleLine = true
            )

            OutlinedTextField(
                value = uiState.appFilter,
                onValueChange = onFilterAppChange,
                modifier = Modifier.fillMaxWidth(),
                label = { Text(text = androidx.compose.ui.res.stringResource(id = R.string.filter_hint)) },
                singleLine = true
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(text = androidx.compose.ui.res.stringResource(id = R.string.auto_dismiss_label))
                Switch(
                    checked = uiState.autoDismissEnabled,
                    onCheckedChange = onAutoDismissChanged
                )
            }

            if (uiState.notifications.isEmpty()) {
                EmptyState()
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(bottom = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(uiState.notifications, key = { it.id }) { notification ->
                        NotificationListItem(
                            notification = notification,
                            onClick = { onOpenDetail(notification.id) }
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun EmptyState() {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = androidx.compose.ui.res.stringResource(id = R.string.empty_state),
            style = MaterialTheme.typography.bodyLarge
        )
    }
}

@Composable
private fun NotificationListItem(
    notification: NotificationEntity,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            Text(
                text = notification.appName,
                style = MaterialTheme.typography.labelLarge
            )
            Text(
                text = if (notification.title.isBlank()) "(No title)" else notification.title,
                style = MaterialTheme.typography.titleMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                text = buildMessagePreview(notification),
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                text = buildTimeSummary(notification),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
private fun NotificationDetailScreen(
    notification: NotificationEntity?,
    onBack: () -> Unit
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(text = "Notification details") },
                navigationIcon = {
                    TextButton(onClick = onBack) {
                        Text(text = "Back")
                    }
                }
            )
        }
    ) { paddingValues ->
        if (notification == null) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues)
                    .padding(16.dp),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(text = "Notification not found")
            }
            return@Scaffold
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Text(text = "App: ${notification.appName}", style = MaterialTheme.typography.titleMedium)
            Text(text = "Package: ${notification.packageName}")
            Text(text = "Title: ${notification.title.ifBlank { "(No title)" }}")
            Text(text = "Message: ${notification.message.ifBlank { "(No message)" }}")
            Text(text = "Big text: ${notification.bigText ?: "-"}")
            Text(text = "Received at: ${formatTime(notification.timestamp)}")
            Text(
                text = "Send at: ${notification.scheduledAt?.let(::formatTime) ?: "Immediate"}"
            )
        }
    }
}

private fun buildMessagePreview(notification: NotificationEntity): String {
    val text = when {
        notification.message.isNotBlank() -> notification.message
        !notification.bigText.isNullOrBlank() -> notification.bigText
        else -> "(No message)"
    }
    return text
}

private fun formatTime(timestamp: Long): String {
    val format = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
    return format.format(Date(timestamp))
}

private fun buildTimeSummary(notification: NotificationEntity): String {
    val received = "Received: ${formatTime(notification.timestamp)}"
    val sendAt = notification.scheduledAt?.let { "Send at: ${formatTime(it)}" } ?: "Send at: Immediate"
    return "$received | $sendAt"
}
