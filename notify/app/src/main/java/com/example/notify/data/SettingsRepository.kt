package com.example.notify.data

import android.content.Context

class SettingsRepository(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun isAutoDismissEnabled(): Boolean = prefs.getBoolean(KEY_AUTO_DISMISS, true)

    fun setAutoDismissEnabled(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_AUTO_DISMISS, enabled).apply()
    }

    companion object {
        private const val PREFS_NAME = "notify_prefs"
        private const val KEY_AUTO_DISMISS = "auto_dismiss"
    }
}
