package com.bhli.audit.mobile

import android.content.pm.ApplicationInfo
import android.content.Intent
import android.os.Bundle
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private lateinit var transferDocuments: TransferDocuments

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (::transferDocuments.isInitialized && transferDocuments.onActivityResult(requestCode, resultCode, data)) return
        super.onActivityResult(requestCode, resultCode, data)
    }

    override fun onDestroy() {
        if (::transferDocuments.isInitialized) transferDocuments.dispose()
        super.onDestroy()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        // Protected Flutter navigation and credentials are never restored.
        super.onCreate(null)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        if (applicationContext.packageName == "com.bhli.audit.offline") {
            transferDocuments = TransferDocuments(this)
            MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "com.bhli.audit/transfer_documents")
                .setMethodCallHandler(transferDocuments)
        }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "com.bhli.audit/privacy")
            .setMethodCallHandler { call, result ->
                if (call.method != "setSecure") {
                    result.notImplemented()
                } else {
                    val debug = applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
                    val secure = !debug || call.argument<Boolean>("secure") != false
                    if (secure) window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
                    else window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
                    result.success(null)
                }
            }
    }
}
