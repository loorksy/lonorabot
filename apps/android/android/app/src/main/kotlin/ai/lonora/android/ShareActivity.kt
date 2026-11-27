package ai.lonora.android

import android.app.Activity
import android.content.Intent
import android.os.Bundle

/**
 * "Send to Lonora" entry point. A UI-less trampoline that forwards the share into the single
 * Lonora task (so the conversation opens in Lonora, not inside the sending app's task) and
 * passes the read grant for shared streams along.
 */
class ShareActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val source = intent
        val forward = Intent(this, MainActivity::class.java).apply {
            action = source.action
            type = source.type
            source.extras?.let { putExtras(it) }
            clipData = source.clipData
            addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK or
                    Intent.FLAG_ACTIVITY_SINGLE_TOP or
                    Intent.FLAG_GRANT_READ_URI_PERMISSION,
            )
        }
        startActivity(forward)
        finish()
    }
}
