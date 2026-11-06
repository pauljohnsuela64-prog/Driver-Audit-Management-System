package com.bhli.audit.mobile

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.SystemClock
import android.provider.DocumentsContract
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileInputStream
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/** Text report output only: no read/import/general-path capability. */
class ReportsDocuments(private val activity: Activity) : MethodChannel.MethodCallHandler {
    private val executor = Executors.newSingleThreadExecutor()
    private val canceled = AtomicBoolean(false)
    private val directory = File(activity.filesDir, "report-staging").apply { mkdirs() }
    private val maximum = 100L * 1024 * 1024
    private val request = 6161
    private var pending: MethodChannel.Result? = null
    private var source: File? = null
    private var started = 0L
    private var remainingMillis = 600000L
    private val generatedName = Regex("[0-9a-f-]{36}\\.txt")
    init {
        executor.execute {
            directory.listFiles()?.forEach { file ->
                if (file.name.matches(generatedName) && file.canonicalFile.parentFile == directory.canonicalFile) file.delete()
            }
        }
    }
    private fun owned(path: String?): File {
        val file = File(path ?: throw IllegalArgumentException()).canonicalFile
        require(file.parentFile == directory.canonicalFile && file.name.matches(generatedName))
        require(file.isFile && file.length() <= maximum)
        return file
    }
    private fun check() {
        if (canceled.get() || SystemClock.elapsedRealtime() - started > remainingMillis) throw InterruptedException()
    }
    private fun finish(saved: Boolean = false, code: String? = null) {
        activity.runOnUiThread {
            val result = pending
            pending = null; source = null
            if (code == null) result?.success(saved)
            else result?.error(code, if (code == "cleanup_incomplete") "An incomplete newly created report may remain." else "Report saving could not finish.", null)
        }
    }
    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "cancel" -> { canceled.set(true); result.success(null) }
            "createStage" -> executor.execute {
                try {
                    val files = directory.listFiles()?.filter { it.name.matches(generatedName) } ?: emptyList()
                    require(files.size < 2 && files.sumOf { it.length() } <= maximum)
                    val file = File(directory, "${UUID.randomUUID()}.txt")
                    require(file.createNewFile())
                    activity.runOnUiThread { result.success(file.path) }
                } catch (_: Exception) { activity.runOnUiThread { result.error("storage", "Private report staging unavailable.", null) } }
            }
            "deleteStage" -> executor.execute {
                try { require(owned(call.argument("path")).delete()); activity.runOnUiThread { result.success(null) } }
                catch (_: Exception) { activity.runOnUiThread { result.error("cleanup", "Private report cleanup failed.", null) } }
            }
            "saveStage" -> {
                if (pending != null) { result.error("busy", "A report save is running.", null); return }
                pending = result; canceled.set(false)
                try {
                    remainingMillis = call.argument<Number>("remainingMillis")?.toLong() ?: 600000L
                    require(remainingMillis in 1L..600000L)
                    source = owned(call.argument("path"))
                    require(source!!.length() > 0)
                    activity.startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT)
                        .addCategory(Intent.CATEGORY_OPENABLE).setType("text/plain")
                        .putExtra(Intent.EXTRA_LOCAL_ONLY, true).putExtra(Intent.EXTRA_TITLE, "BHLI-audit-report.txt"), request)
                } catch (_: Exception) { finish(code = "document") }
            }
            else -> result.notImplemented()
        }
    }
    fun dispose() { canceled.set(true); executor.shutdown() }
    private fun digest(file: File): ByteArray = FileInputStream(file).use { input ->
        val hash = MessageDigest.getInstance("SHA-256"); val buffer = ByteArray(65536); var total = 0L
        while (true) { check(); val n = input.read(buffer); if (n < 0) break; total += n; require(total <= maximum); hash.update(buffer, 0, n) }
        hash.digest()
    }
    fun onActivityResult(code: Int, resultCode: Int, data: Intent?): Boolean {
        if (code != request || pending == null) return false
        val uri = data?.data
        if (resultCode != Activity.RESULT_OK || uri == null) { finish(); return true }
        // This URI comes exclusively from ACTION_CREATE_DOCUMENT. It is a newly
        // created output; no picked source/existing document is ever deleted.
        val newlyCreatedOutput: Uri = uri
        val prepared = source
        executor.execute {
            started = SystemClock.elapsedRealtime()
            try {
                require(uri.scheme == "content"); check()
                val file = prepared ?: throw IllegalStateException()
                val expected = digest(file)
                activity.contentResolver.openOutputStream(uri, "wt")?.use { output ->
                    FileInputStream(file).use { input ->
                        val buffer = ByteArray(65536); var total = 0L
                        while (true) { check(); val n = input.read(buffer); if (n < 0) break; total += n; require(total <= maximum); output.write(buffer, 0, n) }
                    }
                    output.flush()
                } ?: throw IllegalStateException()
                val hash = MessageDigest.getInstance("SHA-256"); var total = 0L
                activity.contentResolver.openInputStream(uri)?.use { input ->
                    val buffer = ByteArray(65536)
                    while (true) { check(); val n = input.read(buffer); if (n < 0) break; total += n; require(total <= maximum); hash.update(buffer, 0, n) }
                } ?: throw IllegalStateException()
                require(MessageDigest.isEqual(expected, hash.digest()))
                // Completion wins over a later cancellation request.
                finish(true)
            } catch (_: Exception) {
                val removed = try { DocumentsContract.deleteDocument(activity.contentResolver, newlyCreatedOutput) } catch (_: Exception) { false }
                finish(code = if (removed) "document" else "cleanup_incomplete")
            }
        }
        return true
    }
}
