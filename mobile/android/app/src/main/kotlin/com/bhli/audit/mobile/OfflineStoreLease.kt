package com.bhli.audit.mobile

import android.content.Context
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.RandomAccessFile
import java.nio.channels.FileLock
import java.util.UUID

/** Process singleton, deliberately independent of Activity/FlutterEngine life. */
object OfflineStoreLease {
    private data class Owner(val token: String, val file: RandomAccessFile, val lock: FileLock)
    private var owner: Owner? = null

    @JvmStatic @Synchronized fun acquire(directory: File): String {
        check(owner == null) { "Close the other offline copy and retry." }
        require(directory.exists() || directory.mkdirs())
        require(directory.canonicalFile == directory.absoluteFile)
        val lockFile = File(directory, "offline-store.owner.lock")
        require(lockFile.canonicalFile == lockFile.absoluteFile)
        val file = RandomAccessFile(lockFile, "rw")
        try {
            val lock = try { file.channel.tryLock() } catch (_: java.nio.channels.OverlappingFileLockException) { null }
            check(lock != null) { "Close the other offline copy and retry." }
            val token = UUID.randomUUID().toString()
            owner = Owner(token, file, lock)
            return token
        } catch (error: Exception) { file.close(); throw error }
    }
    @JvmStatic @Synchronized fun ensureHeld(token: String) {
        val held = owner
        check(held != null && held.token == token && held.lock.isValid && held.file.channel.isOpen) { "Offline storage ownership is unavailable." }
    }
    @JvmStatic @Synchronized fun ensureAnyHeld() {
        val held = owner ?: throw IllegalStateException("Offline storage ownership is unavailable.")
        ensureHeld(held.token)
    }
    @JvmStatic @Synchronized fun release(token: String) {
        ensureHeld(token)
        val held = owner!!
        held.lock.release()
        held.file.close()
        owner = null
        // Keep the inode: removing the lock file allows two independent locks.
    }

    fun handler(context: Context): MethodChannel.MethodCallHandler = MethodChannel.MethodCallHandler { call: MethodCall, result: MethodChannel.Result ->
        try {
            when (call.method) {
                "acquire" -> result.success(acquire(context.getDatabasePath("bhli_offline.db").parentFile!!.canonicalFile))
                "ensureHeld" -> { ensureHeld(call.argument<String>("token") ?: ""); result.success(null) }
                "release" -> { release(call.argument<String>("token") ?: ""); result.success(null) }
                else -> result.notImplemented()
            }
        } catch (_: Exception) { result.error("store_owned", "Close other offline app copies and retry. Local storage ownership could not be obtained or verified.", null) }
    }
}
