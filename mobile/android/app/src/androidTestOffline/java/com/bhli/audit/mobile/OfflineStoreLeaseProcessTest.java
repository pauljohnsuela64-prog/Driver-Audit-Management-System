package com.bhli.audit.mobile;

import static org.junit.Assert.*;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.Message;
import android.os.Messenger;
import android.os.ParcelFileDescriptor;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.Test;

public class OfflineStoreLeaseProcessTest {
    @Test public void competingProcessIsExcludedAndOsReleasesAfterProcessDeath() throws Exception {
        Context target=InstrumentationRegistry.getInstrumentation().getTargetContext();
        Context test=InstrumentationRegistry.getInstrumentation().getContext();
        File dir=new File(target.getCacheDir(),"lease-process-"+UUID.randomUUID()).getCanonicalFile();
        assertTrue(dir.mkdir());
        File lockFile=new File(dir,"offline-store.owner.lock");
        assertTrue(lockFile.createNewFile());
        // Keep this descriptor open until after all parent leases are released:
        // POSIX process locks can be dropped by closing another FD to that inode.
        ParcelFileDescriptor descriptor=ParcelFileDescriptor.open(lockFile,ParcelFileDescriptor.MODE_READ_WRITE);
        AtomicReference<Messenger> remote=new AtomicReference<>();
        CountDownLatch connected=new CountDownLatch(1);
        ServiceConnection connection=new ServiceConnection() {
            @Override public void onServiceConnected(ComponentName name,IBinder binder) { remote.set(new Messenger(binder)); connected.countDown(); }
            @Override public void onServiceDisconnected(ComponentName name) { }
        };
        HandlerThread replies=new HandlerThread("lease-test-replies"); replies.start();
        boolean bound=false;
        String token=null;
        try {
            bound=test.bindService(new Intent(test,OfflineLeaseProbeService.class),connection,Context.BIND_AUTO_CREATE);
            assertTrue(bound); assertTrue(connected.await(10,TimeUnit.SECONDS));
            // Binder may duplicate/close a sender-side FD while parceling it.
            // Transfer it BEFORE acquiring the POSIX lock, then send only
            // descriptor-free control messages while either process holds it.
            assertEquals(1,request(remote.get(),replies,0,descriptor).arg1);
            token=OfflineStoreLease.acquire(dir);
            Message blocked=request(remote.get(),replies,1,null);
            assertEquals(0,blocked.arg1);
            assertNotEquals(android.os.Process.myPid(),blocked.arg2);
            OfflineStoreLease.release(token); token=null;
            assertEquals(1,request(remote.get(),replies,2,null).arg1);
            try { OfflineStoreLease.acquire(dir); fail("remote process owner was bypassed"); }
            catch(IllegalStateException expected) { }
            assertEquals(1,request(remote.get(),replies,3,null).arg1);
            long deadline=android.os.SystemClock.elapsedRealtime()+10000;
            while(token==null && android.os.SystemClock.elapsedRealtime()<deadline) {
                try { token=OfflineStoreLease.acquire(dir); }
                catch(IllegalStateException waitingForOsRelease) { Thread.sleep(50); }
            }
            assertNotNull("OS lease not released after test process death",token);
            OfflineStoreLease.ensureHeld(token);
        } finally {
            if(token!=null) OfflineStoreLease.release(token);
            if(bound) test.unbindService(connection);
            descriptor.close(); replies.quitSafely();
        }
    }
    private Message request(Messenger remote,HandlerThread thread,int action,ParcelFileDescriptor descriptor) throws Exception {
        CountDownLatch received=new CountDownLatch(1); AtomicReference<Message> reply=new AtomicReference<>();
        Messenger response=new Messenger(new Handler(thread.getLooper(),message->{reply.set(Message.obtain(message));received.countDown();return true;}));
        Message request=Message.obtain(); request.what=action; request.replyTo=response;
        if(descriptor!=null) { Bundle data=new Bundle(); data.putParcelable("descriptor",descriptor); request.setData(data); }
        remote.send(request); assertTrue("process probe timed out",received.await(10,TimeUnit.SECONDS));
        return reply.get();
    }
}
