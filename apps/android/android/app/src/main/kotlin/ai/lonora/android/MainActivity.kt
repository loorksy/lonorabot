package ai.lonora.android

import android.app.UiModeManager
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel

/**
 * Edge-to-edge Flutter host.
 *
 * The window draws behind both system bars (Flutter receives raw insets), new links and shares
 * arrive through onNewIntent (singleTop), and the in-app appearance choice also drives native
 * surfaces (splash, IME, system dialogs) through UiModeManager on Android 12+.
 */
class MainActivity : FlutterFragmentActivity() {
    private var shareSink: EventChannel.EventSink? = null
    private var pendingShare: Map<String, Any?>? = null
    private var proximityLock: PowerManager.WakeLock? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        ViewCompat.setOnApplyWindowInsetsListener(window.decorView) { view, insets ->
            view.setPadding(0, 0, 0, 0)
            insets
        }
        pendingShare = SharedContent.read(this, intent)
        super.onCreate(savedInstanceState)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        SharedContent.read(this, intent)?.let { share ->
            val sink = shareSink
            if (sink != null) sink.success(share) else pendingShare = share
        }
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val messenger = flutterEngine.dartExecutor.binaryMessenger

        MethodChannel(messenger, "ai.lonora.android/platform").setMethodCallHandler { call, result ->
            when (call.method) {
                "setNightMode" -> {
                    setNightMode(call.argument<String>("mode") ?: "system")
                    result.success(null)
                }
                "openExternal" -> {
                    val url = call.argument<String>("url")
                    val requireNonBrowser = call.argument<Boolean>("requireNonBrowser") ?: false
                    result.success(url != null && openExternal(url, requireNonBrowser))
                }
                "openNotificationSettings" -> {
                    val intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                        .putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
                    result.success(tryStart(intent))
                }
                "takeInitialShare" -> {
                    result.success(pendingShare)
                    pendingShare = null
                }
                "installerPackage" -> result.success(installerPackage())
                // The phone's IANA zone for quiet hours (Dart has no time-zone database).
                "timeZone" -> result.success(java.util.TimeZone.getDefault().id)
                // Another zone's UTC offset in minutes (the reach-me policy's zone), or null.
                "zoneOffset" -> result.success(
                    zoneOffsetMinutes(
                        call.argument<String>("zone"),
                        call.argument<Number>("at")?.toLong() ?: System.currentTimeMillis(),
                    ),
                )
                // A call on the earpiece: the screen goes off at the ear.
                "proximityScreenOff" -> {
                    setProximityScreenOff(call.argument<Boolean>("on") ?: false)
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }

        EventChannel(messenger, "ai.lonora.android/shares").setStreamHandler(
            object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink) {
                    shareSink = events
                }

                override fun onCancel(arguments: Any?) {
                    shareSink = null
                }
            },
        )
    }

    override fun cleanUpFlutterEngine(flutterEngine: FlutterEngine) {
        shareSink = null
        setProximityScreenOff(false)
        super.cleanUpFlutterEngine(flutterEngine)
    }

    override fun onDestroy() {
        setProximityScreenOff(false)
        super.onDestroy()
    }

    private fun zoneOffsetMinutes(zone: String?, at: Long): Int? =
        try {
            if (zone.isNullOrBlank()) {
                null
            } else {
                java.time.ZoneId.of(zone).rules
                    .getOffset(java.time.Instant.ofEpochMilli(at)).totalSeconds / 60
            }
        } catch (_: Exception) {
            null
        }

    private fun setProximityScreenOff(on: Boolean) {
        val held = proximityLock
        if (on) {
            if (held?.isHeld == true) return
            val power = getSystemService(Context.POWER_SERVICE) as PowerManager
            if (!power.isWakeLockLevelSupported(PowerManager.PROXIMITY_SCREEN_OFF_WAKE_LOCK)) return
            proximityLock = power
                .newWakeLock(PowerManager.PROXIMITY_SCREEN_OFF_WAKE_LOCK, "lonora:call-proximity")
                .apply {
                    setReferenceCounted(false)
                    // Bounded: a call never keeps it past four hours even if the end is missed.
                    acquire(4 * 60 * 60 * 1000L)
                }
        } else if (held != null) {
            // The screen comes back once the phone leaves the ear, not under the cheek.
            if (held.isHeld) held.release(PowerManager.RELEASE_FLAG_WAIT_FOR_NO_PROXIMITY)
            proximityLock = null
        }
    }

    private fun setNightMode(mode: String) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val manager = getSystemService(Context.UI_MODE_SERVICE) as UiModeManager
            manager.setApplicationNightMode(
                when (mode) {
                    "light" -> UiModeManager.MODE_NIGHT_NO
                    "dark" -> UiModeManager.MODE_NIGHT_YES
                    else -> UiModeManager.MODE_NIGHT_AUTO
                },
            )
        }
    }

    private fun openExternal(url: String, requireNonBrowser: Boolean): Boolean {
        val uri = Uri.parse(url)
        if (uri.scheme != "https" && uri.scheme != "http" && uri.scheme != "mailto") return false
        val intent = Intent(Intent.ACTION_VIEW, uri)
            .addCategory(Intent.CATEGORY_BROWSABLE)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (requireNonBrowser && Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            intent.addFlags(Intent.FLAG_ACTIVITY_REQUIRE_NON_BROWSER)
        }
        return tryStart(intent)
    }

    private fun tryStart(intent: Intent): Boolean =
        try {
            startActivity(intent)
            true
        } catch (_: ActivityNotFoundException) {
            false
        }

    private fun installerPackage(): String? =
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                packageManager.getInstallSourceInfo(packageName).installingPackageName
            } else {
                @Suppress("DEPRECATION")
                packageManager.getInstallerPackageName(packageName)
            }
        } catch (_: Exception) {
            null
        }
}
