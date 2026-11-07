package com.bhli.audit.mobile

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import android.provider.DocumentsContract
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.InputStream
import java.io.OutputStream
import java.security.MessageDigest
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/** Backup-only SAF capability. Accepts generated evidence handles, never paths. */
class OfflineDocuments(private val activity: Activity) : MethodChannel.MethodCallHandler {
    private val executor=Executors.newSingleThreadExecutor()
    private val cancelled=AtomicBoolean(false)
    private val evidence=OfflineBackupEvidence(activity)
    private val maximum=OfflineBackupEvidence.MAXIMUM
    private var pending: MethodChannel.Result?=null
    private var source: File?=null
    private var saving=false
    private var started=0L
    private var running=false
    private val openRequest=6162
    private val saveRequest=6163

    private fun finish(handle: String?=null,code: String?=null) {
        activity.runOnUiThread {
            val result=pending
            pending=null; source=null; running=false
            if(code==null) result?.success(handle)
            else result?.error(code,if(code=="cleanup_incomplete")
                "An incomplete newly created backup or private encrypted stage remains. It has not been verified. Retain your original backup and try a new destination."
                else "Backup file selection or saving could not finish. No verified output was advertised.",null)
        }
    }
    private fun check() {
        OfflineStoreLease.ensureAnyHeld()
        if(cancelled.get() || SystemClock.elapsedRealtime()-started>600000L) throw InterruptedException()
    }
    private fun copy(input: InputStream,output: OutputStream): ByteArray {
        val hash=MessageDigest.getInstance("SHA-256")
        val buffer=ByteArray(65536)
        var total=0L
        while(true) {
            check()
            val count=input.read(buffer)
            if(count<0) break
            if(count==0) throw IllegalStateException()
            total+=count
            require(total<=maximum)
            output.write(buffer,0,count)
            hash.update(buffer,0,count)
        }
        require(total>0)
        return hash.digest()
    }
    private fun digest(file: File): ByteArray = FileInputStream(file).use { input ->
        val hash=MessageDigest.getInstance("SHA-256"); val buffer=ByteArray(65536); var total=0L
        while(true) {
            check(); val count=input.read(buffer); if(count<0) break
            if(count==0) throw IllegalStateException()
            total+=count; require(total<=maximum); hash.update(buffer,0,count)
        }
        require(total>0); hash.digest()
    }
    override fun onMethodCall(call: MethodCall,result: MethodChannel.Result) {
        when(call.method) {
            "cancel" -> { cancelled.set(true); result.success(null) }
            "pickBackup", "saveBackup" -> {
                if(pending!=null) { result.error("busy","Another backup file operation is running.",null); return }
                pending=result; cancelled.set(false); saving=call.method=="saveBackup"
                try {
                    OfflineStoreLease.ensureAnyHeld()
                    source=if(saving) OfflineBackupEvidence.owned(activity,call.argument<String>("handle") ?: "") else null
                    if(saving) require(source!!.length()>0)
                    val intent=Intent(if(saving) Intent.ACTION_CREATE_DOCUMENT else Intent.ACTION_OPEN_DOCUMENT)
                        .addCategory(Intent.CATEGORY_OPENABLE).setType(if(saving) "application/octet-stream" else "*/*")
                        .putExtra(Intent.EXTRA_LOCAL_ONLY,true)
                    if(saving) {
                        val title=call.argument<String>("name") ?: "BHLI-backup.bhlibackup"
                        require(Regex("[A-Za-z0-9._-]{1,96}\\.bhlibackup").matches(title))
                        intent.putExtra(Intent.EXTRA_TITLE,title)
                    }
                    activity.startActivityForResult(intent,if(saving) saveRequest else openRequest)
                } catch(_: Exception) { finish(code="document") }
            }
            else -> result.notImplemented()
        }
    }
    /** Cancellation does not release the process-owned SQLite lease. */
    fun dispose() { cancelled.set(true); executor.shutdown() }
    fun onActivityResult(code: Int,resultCode: Int,data: Intent?): Boolean {
        if(pending==null || (saving && code!=saveRequest) || (!saving && code!=openRequest)) return false
        val uri=data?.data
        if(resultCode!=Activity.RESULT_OK || uri==null) { finish(); return true }
        // Only the CREATE_DOCUMENT result may populate deletion authority.
        val newlyCreatedOutput: Uri?=if(saving) uri else null
        val prepared=source
        running=true
        executor.execute {
            var staged: File?=null
            started=SystemClock.elapsedRealtime()
            try {
                require(uri.scheme=="content"); check()
                val expected=if(newlyCreatedOutput!=null) {
                    val file=prepared ?: throw IllegalStateException()
                    val originalHash=digest(file)
                    val descriptor=activity.contentResolver.openFileDescriptor(uri,"wt") ?: throw IllegalStateException()
                    ParcelFileDescriptor.AutoCloseOutputStream(descriptor).use { output ->
                        FileInputStream(file).use { input -> copy(input,output) }
                        output.flush()
                        // Provider pipes/unsupported sync fail closed, never silently weaken durability.
                        output.fd.sync()
                    }
                    originalHash
                } else null
                val readback=evidence.create(); staged=readback
                val copied=activity.contentResolver.openInputStream(uri)?.use { input ->
                    FileOutputStream(readback).use { output ->
                        val hash=copy(input,output); output.flush(); output.fd.sync(); hash
                    }
                } ?: throw IllegalStateException()
                evidence.sync(readback.name)
                require(MessageDigest.isEqual(copied,digest(readback)))
                if(expected!=null) require(MessageDigest.isEqual(expected,copied))
                // Retain this verified encrypted input/readback for core authentication.
                // A later cancellation cannot undo a completed save.
                finish(readback.name)
            } catch(_: Exception) {
                val privateRemoved=staged?.let { !it.exists() || it.delete() } ?: true
                val publicRemoved=if(newlyCreatedOutput==null) true else try {
                    DocumentsContract.deleteDocument(activity.contentResolver,newlyCreatedOutput)
                } catch(_: Exception) { false }
                finish(code=if(privateRemoved && publicRemoved) "document" else "cleanup_incomplete")
            }
        }
        return true
    }
}
