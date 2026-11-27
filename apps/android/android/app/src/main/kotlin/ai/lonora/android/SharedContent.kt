package ai.lonora.android

import android.content.Context
import android.content.Intent
import android.database.Cursor
import android.net.Uri
import android.os.Build
import android.provider.OpenableColumns
import java.io.File
import java.util.UUID

/**
 * Normalises "Share to Lonora" intents into a plain map for Dart:
 * {"text": String?, "files": [{"path", "name", "mimeType", "size"}]}.
 *
 * Shared streams are copied into the app's cache (shares/) so Dart can upload them as message
 * attachments after the sender's URI permission expires. Nothing is uploaded automatically: the
 * owner chooses the conversation and sends.
 */
object SharedContent {
    private const val MAX_FILES = 10
    private const val MAX_BYTES = 50L * 1024 * 1024

    fun read(context: Context, intent: Intent?): Map<String, Any?>? {
        if (intent == null) return null
        val action = intent.action ?: return null
        if (action != Intent.ACTION_SEND && action != Intent.ACTION_SEND_MULTIPLE) return null
        if (intent.getBooleanExtra(CONSUMED, false)) return null
        intent.putExtra(CONSUMED, true)

        val text = intent.getStringExtra(Intent.EXTRA_TEXT)?.takeIf { it.isNotBlank() }
        val uris = mutableListOf<Uri>()
        if (action == Intent.ACTION_SEND) {
            streamExtra(intent)?.let { uris.add(it) }
        } else {
            streamListExtra(intent)?.let { uris.addAll(it) }
        }
        val files = uris.take(MAX_FILES).mapNotNull { copyToCache(context, it, intent.type) }
        if (text == null && files.isEmpty()) return null
        return mapOf("text" to text, "files" to files)
    }

    private fun streamExtra(intent: Intent): Uri? =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent.getParcelableExtra(Intent.EXTRA_STREAM)
        }

    private fun streamListExtra(intent: Intent): List<Uri>? =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM)
        }

    private fun copyToCache(context: Context, uri: Uri, fallbackType: String?): Map<String, Any?>? {
        if (uri.scheme != "content") return null
        val resolver = context.contentResolver
        var name = "shared"
        var declaredSize = -1L
        resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c: Cursor ->
            if (c.moveToFirst()) {
                c.getString(0)?.let { name = it }
                if (!c.isNull(1)) declaredSize = c.getLong(1)
            }
        }
        if (declaredSize > MAX_BYTES) return null
        val safeName = name.replace(Regex("[^\\p{L}\\p{N}._ -]"), "_").take(120).ifBlank { "shared" }
        val dir = File(context.cacheDir, "shares/${UUID.randomUUID()}").apply { mkdirs() }
        val target = File(dir, safeName)
        var copied = 0L
        try {
            resolver.openInputStream(uri)?.use { input ->
                target.outputStream().use { output ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        val read = input.read(buffer)
                        if (read < 0) break
                        copied += read
                        if (copied > MAX_BYTES) throw IllegalStateException("too large")
                        output.write(buffer, 0, read)
                    }
                }
            } ?: return null
        } catch (_: Exception) {
            dir.deleteRecursively()
            return null
        }
        val mime = resolver.getType(uri) ?: fallbackType ?: "application/octet-stream"
        return mapOf("path" to target.absolutePath, "name" to safeName, "mimeType" to mime, "size" to copied)
    }

    private const val CONSUMED = "ai.lonora.android.share_consumed"
}
