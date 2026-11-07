package com.bhli.audit.mobile;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.ContentResolver;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.provider.DocumentsContract;
import androidx.test.platform.app.InstrumentationRegistry;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import static org.junit.Assert.*;

/** Real report bridge fault injection. System picker grants and successful readback need SAF acceptance. */
public final class OfflineDocumentsSafetyTest {
    private Instrumentation instrumentation;
    private OfflineDocuments bridge;
    private ContentResolver resolver;
    private File stage;
    private String leaseToken;
    private static final Uri CONTROL = Uri.parse("content://" + TransferFaultDocumentsProvider.AUTHORITY);

    private static final class Result implements MethodChannel.Result {
        final CountDownLatch done = new CountDownLatch(1);
        Object value;
        String error;
        int successes;
        @Override public void success(Object value) { this.value = value; successes++; done.countDown(); }
        @Override public void error(String code, String message, Object details) { error = code; done.countDown(); }
        @Override public void notImplemented() { error = "notImplemented"; done.countDown(); }
        void await() throws InterruptedException {
            assertTrue("Native report callback timed out", done.await(15, TimeUnit.SECONDS));
        }
    }

    @Before public void setUp() throws Exception {
        instrumentation = InstrumentationRegistry.getInstrumentation();
        resolver = instrumentation.getTargetContext().getContentResolver();
        instrumentation.runOnMainSync(() -> {
            TransferDocumentsTestActivity activity = new TransferDocumentsTestActivity();
            activity.bind(instrumentation.getTargetContext());
            bridge = new OfflineDocuments(activity);
            try { stage = new OfflineBackupEvidence(activity).create(); } catch (Exception failure) { throw new AssertionError(failure); }
        });
        File directory = new File(instrumentation.getTargetContext().getCacheDir(), "backup-docs-lease-" + UUID.randomUUID());
        assertTrue(directory.mkdir());
        leaseToken = OfflineStoreLease.acquire(directory.getCanonicalFile());
        reset(false);
        try (FileOutputStream output = new FileOutputStream(stage)) {
            output.write("Fictional report: 00123 日本語 🚚\n".getBytes(StandardCharsets.UTF_8));
            output.flush();
            output.getFD().sync();
        }
    }

    @After public void tearDown() throws Exception {
        if (bridge != null) {
            if (stage != null && stage.exists()) {
                assertTrue(stage.delete());
            }
            instrumentation.runOnMainSync(() -> bridge.dispose());
        }
        if (leaseToken != null) OfflineStoreLease.release(leaseToken);
    }

    private Result invoke(String method, Object arguments) throws Exception {
        Result result = new Result();
        instrumentation.runOnMainSync(() -> bridge.onMethodCall(new MethodCall(method, arguments), result));
        result.await();
        return result;
    }

    private void reset(boolean failDelete) {
        Bundle options = new Bundle();
        options.putBoolean("failDelete", failDelete);
        assertNotNull(resolver.call(CONTROL, "reset", null, options));
    }

    private Bundle counts() { return resolver.call(CONTROL, "counts", null, null); }

    private void field(String name, Object value) {
        try {
            Field field = OfflineDocuments.class.getDeclaredField(name);
            field.setAccessible(true);
            field.set(bridge, value);
        } catch (ReflectiveOperationException failure) { throw new AssertionError(failure); }
    }

    // Inject only the picker completion, just as TransferDocumentsSafetyTest does;
    // never launch an external picker from the context-bound test Activity.
    private Result deliver(int resultCode, String document) throws Exception {
        Result result = new Result();
        instrumentation.runOnMainSync(() -> {
            field("pending", result);
            field("source", stage);
            field("saving", true);
            Intent data = document == null ? null : new Intent().setData(
                DocumentsContract.buildDocumentUri(TransferFaultDocumentsProvider.AUTHORITY, document));
            assertTrue(bridge.onActivityResult(6163, resultCode, data));
        });
        result.await();
        return result;
    }

    @Test public void stageIsGeneratedPrivateAndUnownedPathsAreRejected() throws Exception {
        assertTrue(stage.isFile());
        assertEquals("backup-evidence", stage.getParentFile().getName());
        assertTrue(stage.getName().matches("[0-9a-f-]{36}\\.bhlibackup"));
        // A plausible generated basename outside the owned directory is still forbidden.
        File outside = new File(stage.getParentFile().getParentFile(), UUID.randomUUID() + ".bhlibackup");
        try {
            try (FileOutputStream output = new FileOutputStream(outside)) { output.write(1); }
            Result saved = invoke("saveBackup", Collections.singletonMap("handle", outside.getPath()));
            assertEquals("document", saved.error);
            assertEquals(0, saved.successes);
            assertTrue(outside.exists());
            assertTrue(stage.exists());
            Bundle count = counts();
            assertEquals(0, count.getInt("opens"));
            assertEquals(0, count.getInt("newDeletes"));
            assertEquals(0, count.getInt("existingDeletes"));
        } finally { assertTrue(outside.delete()); }
    }

    @Test public void canceledPickerDoesNotOpenOrDeleteDocuments() throws Exception {
        // Ignore even a stray returned URI when the system says selection was canceled.
        Result result = deliver(Activity.RESULT_CANCELED, "existing");
        assertNull(result.error);
        assertEquals(1, result.successes);
        assertNull(result.value);
        assertTrue(stage.exists());
        Bundle count = counts();
        assertEquals(0, count.getInt("opens"));
        assertEquals(0, count.getInt("newDeletes"));
        assertEquals(0, count.getInt("existingDeletes"));
    }

    @Test public void outputFailureDeletesOnlyNewDocumentAndPreservesStage() throws Exception {
        Result result = deliver(Activity.RESULT_OK, "new");
        assertEquals("document", result.error);
        assertEquals(0, result.successes);
        assertTrue(stage.exists());
        Bundle count = counts();
        assertEquals(1, count.getInt("opens"));
        assertEquals(1, count.getInt("newDeletes"));
        assertEquals(0, count.getInt("existingDeletes"));
    }

    @Test public void cleanupFailureReportsIncompleteAndNeverSuccess() throws Exception {
        reset(true);
        Result result = deliver(Activity.RESULT_OK, "new");
        assertEquals("cleanup_incomplete", result.error);
        assertEquals(0, result.successes);
        assertTrue(stage.exists());
        Bundle count = counts();
        assertEquals(1, count.getInt("opens"));
        assertEquals(1, count.getInt("newDeletes"));
        assertEquals(0, count.getInt("existingDeletes"));
    }
}
