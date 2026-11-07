package com.bhli.audit.mobile;

import android.app.Service;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.Message;
import android.os.Messenger;
import android.os.ParcelFileDescriptor;
import java.io.FileOutputStream;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;

/** Test APK only; accepts an already-granted FD, never a filesystem path. */
public final class OfflineLeaseProbeService extends Service {
    private FileOutputStream heldStream;
    private FileLock heldLock;
    private final Handler handler = new Handler(Looper.getMainLooper(), message -> {
        Message response = Message.obtain();
        response.what = message.what;
        response.arg2 = android.os.Process.myPid();
        try {
            if (message.what == 3) {
                response.arg1 = 1;
                message.replyTo.send(response);
                new Handler(Looper.getMainLooper()).postDelayed(() -> android.os.Process.killProcess(android.os.Process.myPid()),100);
                return true;
            }
            if(message.what==0) {
                ParcelFileDescriptor descriptor=message.getData().getParcelable("descriptor");
                if(descriptor==null || heldStream!=null) throw new IllegalArgumentException();
                heldStream=new ParcelFileDescriptor.AutoCloseOutputStream(descriptor);
                response.arg1=1;
                message.replyTo.send(response);
                return true;
            }
            if(heldStream==null) throw new IllegalStateException();
            FileOutputStream stream=heldStream;
            FileLock lock;
            try { lock = stream.getChannel().tryLock(); }
            catch (OverlappingFileLockException expected) { lock = null; }
            response.arg1 = lock == null ? 0 : 1;
            if (message.what == 2 && lock != null) { heldStream = stream; heldLock = lock; }
            else { if (lock != null) lock.release(); }
        } catch (Exception failure) { response.arg1 = -1; }
        try { message.replyTo.send(response); } catch (Exception ignored) { }
        return true;
    });
    private final Messenger messenger = new Messenger(handler);
    @Override public IBinder onBind(Intent intent) { return messenger.getBinder(); }
    @Override public void onDestroy() {
        try { if(heldLock != null) heldLock.release(); } catch(Exception ignored) { }
        try { if(heldStream != null) heldStream.close(); } catch(Exception ignored) { }
        super.onDestroy();
    }
}
