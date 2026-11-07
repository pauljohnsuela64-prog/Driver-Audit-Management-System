package com.bhli.audit.mobile

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.system.Os
import android.system.OsConstants
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.util.UUID
import java.util.concurrent.Executors

/** Retained encrypted evidence only. There is no orphan cleanup or source delete. */
class OfflineBackupEvidence(private val context: Context) : MethodChannel.MethodCallHandler {
    companion object {
        const val MAXIMUM = 64L * 1024 * 1024 + 112
        private val generated = Regex("[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\\.bhlibackup")
        private fun directory(context: Context): File {
            val directory = File(context.filesDir.canonicalFile, "backup-evidence")
            require(directory.exists() || directory.mkdirs())
            require(directory.canonicalFile == directory.absoluteFile && directory.isDirectory)
            return directory
        }
        @JvmStatic fun owned(context: Context, handle: String): File {
            require(generated.matches(handle))
            val directory = directory(context)
            val file = File(directory, handle)
            require(file.canonicalFile == file.absoluteFile && file.canonicalFile.parentFile == directory.canonicalFile)
            require(file.isFile && file.length() <= MAXIMUM)
            return file
        }
        private fun syncDirectory(directory: File) {
            val descriptor = Os.open(directory.path, OsConstants.O_RDONLY, 0)
            try { require(OsConstants.S_ISDIR(Os.fstat(descriptor).st_mode)); Os.fsync(descriptor) } finally { Os.close(descriptor) }
        }
    }
    private val executor = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val markerName = "restore-pending.json"
    private fun marker(): File {
        val file = File(directory(context), markerName)
        require(file.canonicalFile == file.absoluteFile)
        return file
    }
    fun create(): File {
        val directory = directory(context)
        val files = directory.listFiles() ?: throw IllegalStateException()
        require(files.size < 4096 && files.sumOf { if(it.isFile) it.length() else 0L } + MAXIMUM <= 512L * 1024 * 1024)
        require(directory.usableSpace > MAXIMUM * 2)
        val file = File(directory, "${UUID.randomUUID()}.bhlibackup")
        check(file.createNewFile())
        syncDirectory(directory)
        return file
    }
    fun sync(handle: String) {
        val file = owned(context,handle)
        FileOutputStream(file,true).use { it.flush(); it.fd.sync() }
        syncDirectory(file.parentFile!!)
    }
    fun readMarker(): ByteArray? {
        val file = marker()
        if (!file.exists()) return null
        require(file.isFile && file.length() <= 4096)
        FileInputStream(file).use { input ->
            val buffer = ByteArray(4097)
            var length=0
            while(length < buffer.size) {
                val count=input.read(buffer,length,buffer.size-length)
                if(count<0) break
                if(count==0) throw IllegalStateException()
                length+=count
            }
            require(length<=4096)
            return buffer.copyOf(length)
        }
    }
    fun writeMarker(bytes: ByteArray) {
        require(bytes.isNotEmpty() && bytes.size <= 4096)
        val file = marker()
        check(!file.exists()) { "A pending recovery operation already exists." }
        check(file.createNewFile())
        // A failed/truncated marker remains blocking evidence; never erase it.
        FileOutputStream(file).use { output -> output.write(bytes); output.flush(); output.fd.sync() }
        syncDirectory(file.parentFile!!)
        check(readMarker()!!.contentEquals(bytes))
    }
    fun clearMarker() {
        val file = marker()
        if (file.exists()) check(file.delete())
        syncDirectory(file.parentFile!!)
    }
    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        executor.execute {
            try {
                OfflineStoreLease.ensureAnyHeld()
                val value: Any? = when(call.method) {
                    "createEvidence" -> { val file=create(); mapOf("handle" to file.name,"path" to file.path) }
                    "syncEvidence" -> { sync(call.argument<String>("handle") ?: ""); null }
                    "readEvidencePath" -> owned(context,call.argument<String>("handle") ?: "").path
                    "readMarker" -> readMarker()
                    "writeMarker" -> { writeMarker(call.argument<ByteArray>("bytes") ?: throw IllegalArgumentException()); null }
                    "clearMarker" -> { clearMarker(); null }
                    else -> { main.post { result.notImplemented() }; return@execute }
                }
                main.post { result.success(value) }
            } catch (_: Exception) { main.post { result.error("recovery_evidence", "Private encrypted recovery evidence could not be safely saved or verified. Retain all recovery files.", null) } }
        }
    }
}
