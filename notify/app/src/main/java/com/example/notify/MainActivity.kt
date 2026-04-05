package com.example.notify

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import androidx.core.app.NotificationManagerCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.notify.ui.NotificationInboxApp
import com.example.notify.ui.theme.NotifyTheme
import com.example.notify.util.UsageAccessHelper
import com.example.notify.viewmodel.NotificationViewModel
import com.example.notify.viewmodel.NotificationViewModelFactory

class MainActivity : ComponentActivity() {
    private val viewModel: NotificationViewModel by viewModels {
        val app = application as NotifyApplication
        NotificationViewModelFactory(app.notificationRepository, app.settingsRepository)
    }

    private var notificationAccessEnabled by mutableStateOf(false)
    private var usageAccessEnabled by mutableStateOf(false)

    private val requestCalendarPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    private val requestPostNotificationsPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        requestPermissionsIfNeeded()
        setContent {
            val uiState by viewModel.uiState.collectAsStateWithLifecycle()

            NotifyTheme {
                NotificationInboxApp(
                    uiState = uiState,
                    notificationAccessEnabled = notificationAccessEnabled,
                    usageAccessEnabled = usageAccessEnabled,
                    onOpenNotificationAccessSettings = {
                        startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                    },
                    onOpenUsageAccessSettings = {
                        startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
                    },
                    onClearAll = viewModel::clearAll,
                    onSearchQueryChange = viewModel::updateSearchQuery,
                    onFilterAppChange = viewModel::updateAppFilter,
                    onAutoDismissChanged = viewModel::setAutoDismissEnabled,
                    detailFlowProvider = viewModel::notificationById
                )
            }
        }
    }

    override fun onResume() {
        super.onResume()
        requestPermissionsIfNeeded()
        notificationAccessEnabled = NotificationManagerCompat
            .getEnabledListenerPackages(this)
            .contains(packageName)
        usageAccessEnabled = UsageAccessHelper.hasUsageAccess(this)
    }

    private fun requestPermissionsIfNeeded() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CALENDAR)
            != PackageManager.PERMISSION_GRANTED
        ) {
            requestCalendarPermission.launch(Manifest.permission.READ_CALENDAR)
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        ) {
            requestPostNotificationsPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }
}