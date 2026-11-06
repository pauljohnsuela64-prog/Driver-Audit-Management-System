package com.bhli.audit.mobile

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class TransferDocuments(private val activity: Activity) : MethodChannel.MethodCallHandler {
    private val executor = Executors.newSingleThreadExecutor()
    private val canceled = AtomicBoolean(false)
    private val directory = File(activity.filesDir, "transfer-staging").apply { mkdirs() }
    private var pending: MethodChannel.Result? = null
    private var source: File? = null
    private var requestedAction: String? = null
    private val maximum = 32L * 1024 * 1024
    private val openRequest = 6151
    private val createRequest = 6152
    init {
        // A fresh activity owns a fresh operation; remove only generated orphan
        // stages inside this exact app-private directory after process restart.
        executor.execute {
            directory.listFiles()?.forEach { file ->
                if (file.name.matches(Regex("[0-9a-f-]{36}\\.bhlitransfer")) &&
                    file.canonicalFile.parentFile == directory.canonicalFile) file.delete()
            }
        }
    }
    private fun generated(): File {
        val owned = directory.listFiles()?.filter { it.name.matches(Regex("[0-9a-f-]{36}\\.bhlitransfer")) } ?: emptyList()
        require(owned.size < 4 && owned.sumOf { it.length() } <= maximum)
        return File(directory, "${UUID.randomUUID()}.bhlitransfer").apply { require(createNewFile()) }
    }
    private fun privateFile(path: String?): File {
        val file = File(path ?: throw IllegalArgumentException()).canonicalFile
        require(file.parentFile == directory.canonicalFile && file.name.matches(Regex("[0-9a-f-]{36}\\.bhlitransfer")))
        require(file.isFile && file.length() <= maximum)
        return file
    }
    private fun finish(value: Any? = null, code: String? = null) {
        activity.runOnUiThread {
            val result = pending
            pending = null; source = null; requestedAction = null
            if (code == null) result?.success(value)
            else result?.error(code, if (code == "cleanup_incomplete") "Saving failed. An incomplete document may remain." else "Transfer could not finish. Choose a valid local file and retry.", null)
        }
    }
    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "cancel" -> { canceled.set(true); result.success(null) }
            "deleteStage" -> executor.execute {
                try { require(privateFile(call.argument("path")).delete()); activity.runOnUiThread { result.success(null) } }
                catch (_: Exception) { activity.runOnUiThread { result.error("cleanup", "Private transfer cleanup failed.", null) } }
            }
            "createStage" -> executor.execute {
                try { val file = generated(); activity.runOnUiThread { result.success(file.path) } }
                catch (_: Exception) { activity.runOnUiThread { result.error("storage", "Private transfer staging is unavailable.", null) } }
            }
            "pickImport", "saveStage" -> {
                if (pending != null) { result.error("busy", "Another document transfer is running.", null); return }
                canceled.set(false); pending = result
                val saving = call.method == "saveStage"
                try {
                    source = if (saving) privateFile(call.argument("path")) else null
                    requestedAction = if (saving) Intent.ACTION_CREATE_DOCUMENT else Intent.ACTION_OPEN_DOCUMENT
                    val intent = Intent(requestedAction).addCategory(Intent.CATEGORY_OPENABLE)
                        .setType(if (saving) "application/octet-stream" else "*/*").putExtra(Intent.EXTRA_LOCAL_ONLY, true)
                    if (saving) intent.putExtra(Intent.EXTRA_TITLE, "BHLI-audits.bhlitransfer")
                    activity.startActivityForResult(intent, if (saving) createRequest else openRequest)
                } catch (_: Exception) { finish(code = "document") }
            }
            else -> result.notImplemented()
        }
    }
    fun dispose() { canceled.set(true); executor.shutdown() }
    private fun checkCancel() { if (canceled.get()) throw InterruptedException() }
    private fun digest(file: File): ByteArray = FileInputStream(file).use { input ->
        val hash = MessageDigest.getInstance("SHA-256"); val buffer = ByteArray(65536); var total = 0L
        while (true) { checkCancel(); val count = input.read(buffer); if (count < 0) break; total += count; require(total <= maximum); hash.update(buffer, 0, count) }
        hash.digest()
    }
    private fun verify(uri: Uri, expected: ByteArray) {
        val hash = MessageDigest.getInstance("SHA-256"); var total = 0L
        activity.contentResolver.openInputStream(uri)?.use { input ->
            val buffer = ByteArray(65536)
            while (true) { checkCancel(); val count = input.read(buffer); if (count < 0) break; total += count; require(total <= maximum); hash.update(buffer, 0, count) }
        } ?: throw IllegalStateException()
        require(MessageDigest.isEqual(expected, hash.digest()))
    }
    fun onActivityResult(code: Int, resultCode: Int, data: Intent?): Boolean {
        if ((code != openRequest && code != createRequest) || pending == null) return false
        val saving = code == createRequest && requestedAction == Intent.ACTION_CREATE_DOCUMENT
        if (!saving && (code != openRequest || requestedAction != Intent.ACTION_OPEN_DOCUMENT)) return false
        val uri = data?.data
        if (resultCode != Activity.RESULT_OK || uri == null) { finish(if (saving) false else null); return true }
        // Only ACTION_CREATE_DOCUMENT can populate this variable. Android guarantees
        // this action creates a new file and cannot overwrite an existing document:
        // https://developer.android.com/training/data-storage/shared/documents-files#create-file
        val newlyCreatedDocument: Uri? = if (saving) uri else null
        val prepared = source
        executor.execute {
            var staged: File? = null
            try {
                require(uri.scheme == "content"); checkCancel()
                if (newlyCreatedDocument != null) {
                    val file = prepared ?: throw IllegalStateException(); val expected = digest(file)
                    activity.contentResolver.openOutputStream(newlyCreatedDocument, "wt")?.use { output ->
                            FileInputStream(file).use { input ->
                                val buffer = ByteArray(65536); var total = 0L
                                while (true) { checkCancel(); val count = input.read(buffer); if (count < 0) break; total += count; require(total <= maximum); output.write(buffer, 0, count) }
                            }
                            output.flush()
                    } ?: throw IllegalStateException()
                    verify(newlyCreatedDocument, expected); finish(true)
                } else {
                    val file = generated(); staged = file; val expected = MessageDigest.getInstance("SHA-256")
                    activity.contentResolver.openInputStream(uri)?.use { input ->
                        FileOutputStream(file).use { output ->
                            val buffer = ByteArray(65536); var total = 0L
                            while (true) { checkCancel(); val count = input.read(buffer); if (count < 0) break; total += count; require(total <= maximum); output.write(buffer, 0, count); expected.update(buffer, 0, count) }
                            output.flush(); output.fd.sync()
                        }
                    } ?: throw IllegalStateException()
                    require(MessageDigest.isEqual(expected.digest(), digest(file))); finish(file.path)
                }
            } catch (_: Exception) {
                staged?.delete()
                val removed = if (newlyCreatedDocument == null) true else try {
                    // Approved transfer spec: delete only the newly created document on failure.
                    DocumentsContract.deleteDocument(activity.contentResolver, newlyCreatedDocument)
                } catch (_: Exception) { false }
                finish(code = if (removed) "document" else "cleanup_incomplete")
            }
        }
        return true
    }
}
