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
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import static org.junit.Assert.*;

/** Real bridge/ContentResolver fault injection using a virtual document provider. OS grants are covered by the SAF UI suite. */
public final class TransferDocumentsSafetyTest {
    private Instrumentation instrumentation;
    private TransferDocuments bridge;
    private ContentResolver resolver;
    private File stage;
    private static final Uri CONTROL = Uri.parse("content://" + TransferFaultDocumentsProvider.AUTHORITY);
    private static final class Result implements MethodChannel.Result {
        final CountDownLatch done = new CountDownLatch(1);
        Object value;
        String error;
        int successes;
        @Override public void success(Object value) { this.value = value; successes++; done.countDown(); }
        @Override public void error(String code, String message, Object details) { error = code; done.countDown(); }
        @Override public void notImplemented() { error = "notImplemented"; done.countDown(); }
        void await() throws InterruptedException { assertTrue("Native callback timed out", done.await(15, TimeUnit.SECONDS)); }
    }
    @Before public void setUp() throws Exception {
        instrumentation = InstrumentationRegistry.getInstrumentation();


        resolver = instrumentation.getTargetContext().getContentResolver();
        instrumentation.runOnMainSync(() -> {
            TransferDocumentsTestActivity activity = new TransferDocumentsTestActivity();
            activity.bind(instrumentation.getTargetContext());
            bridge = new TransferDocuments(activity);
        });
        reset(false);
        Result created = new Result();
        instrumentation.runOnMainSync(() -> bridge.onMethodCall(new MethodCall("createStage", null), created));
        created.await();
        assertNull(created.error);
        assertTrue(created.value instanceof String);
        stage = new File((String) created.value);
        try (FileOutputStream output = new FileOutputStream(stage)) {
            output.write("fictional-owned-transfer".getBytes(StandardCharsets.UTF_8));
            output.flush(); output.getFD().sync();
        }
    }
    @After public void tearDown() throws Exception {
        if (bridge != null) {
            if (stage != null && stage.exists()) {
                Result deleted = new Result();
                instrumentation.runOnMainSync(() -> bridge.onMethodCall(new MethodCall("deleteStage", java.util.Collections.singletonMap("path", stage.getPath())), deleted));
                deleted.await(); assertNull(deleted.error);
            }
            instrumentation.runOnMainSync(() -> bridge.dispose());
        }

    }
    private void reset(boolean failDelete) {
        Bundle options = new Bundle(); options.putBoolean("failDelete", failDelete);
        assertNotNull(resolver.call(CONTROL, "reset", null, options));
    }
    private Bundle counts() { return resolver.call(CONTROL, "counts", null, null); }
    private void field(String name, Object value) {
        try { Field f = TransferDocuments.class.getDeclaredField(name); f.setAccessible(true); f.set(bridge, value); }
        catch (ReflectiveOperationException failure) { throw new AssertionError(failure); }
    }
    private Result deliver(boolean saving, int resultCode, String document) throws Exception {
        Result result = new Result();
        instrumentation.runOnMainSync(() -> {
            field("pending", result);
            field("source", saving ? stage : null);
            field("requestedAction", saving ? Intent.ACTION_CREATE_DOCUMENT : Intent.ACTION_OPEN_DOCUMENT);
            Intent data = document == null ? null : new Intent().setData(
                DocumentsContract.buildDocumentUri(TransferFaultDocumentsProvider.AUTHORITY, document));
            assertTrue(bridge.onActivityResult(saving ? 6152 : 6151, resultCode, data));
        });
        result.await(); return result;
    }
    @Test public void openFailureNeverDeletesExistingDocument() throws Exception {
        Result result = deliver(false, Activity.RESULT_OK, "existing");
        assertEquals("document", result.error); assertEquals(0, result.successes);
        Bundle count = counts(); assertEquals(1, count.getInt("opens"));
        assertEquals(0, count.getInt("existingDeletes")); assertEquals(0, count.getInt("newDeletes"));
    }
    @Test public void createOutputFailureDeletesOnlyNewDocument() throws Exception {
        Result result = deliver(true, Activity.RESULT_OK, "new");
        assertEquals("document", result.error); assertEquals(0, result.successes);
        Bundle count = counts(); assertEquals(1, count.getInt("opens"));
        assertEquals(1, count.getInt("newDeletes")); assertEquals(0, count.getInt("existingDeletes"));
    }
    @Test public void cleanupFailureReportsIncompleteAndNeverSuccess() throws Exception {
        reset(true);
        Result result = deliver(true, Activity.RESULT_OK, "new");
        assertEquals("cleanup_incomplete", result.error); assertEquals(0, result.successes);
        Bundle count = counts(); assertEquals(1, count.getInt("newDeletes"));
        assertEquals(0, count.getInt("existingDeletes"));
    }
    @Test public void canceledPickersNeverDeleteAnyDocument() throws Exception {
        for (boolean saving : new boolean[]{false, true}) {
            Result result = deliver(saving, Activity.RESULT_CANCELED, null);
            assertNull(result.error); assertEquals(1, result.successes);
            assertEquals(saving ? Boolean.FALSE : null, result.value);
        }
        Bundle count = counts(); assertEquals(0, count.getInt("opens"));
        assertEquals(0, count.getInt("newDeletes")); assertEquals(0, count.getInt("existingDeletes"));
    }
}
