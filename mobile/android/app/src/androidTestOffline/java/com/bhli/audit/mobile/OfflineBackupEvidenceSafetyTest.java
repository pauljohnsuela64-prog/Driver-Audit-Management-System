package com.bhli.audit.mobile;

import static org.junit.Assert.*;
import androidx.test.platform.app.InstrumentationRegistry;
import android.content.Context;
import android.content.ContextWrapper;
import java.util.UUID;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import org.junit.Test;

public class OfflineBackupEvidenceSafetyTest {
    private Context isolatedContext() throws Exception {
        Context target = InstrumentationRegistry.getInstrumentation().getTargetContext();
        final File root = new File(target.getCacheDir(), "evidence-test-" + UUID.randomUUID()).getCanonicalFile();
        assertTrue(root.mkdir());
        return new ContextWrapper(target) { @Override public File getFilesDir() { return root; } };
    }
    @Test public void evidenceNamesAreGeneratedAndPathEscapeIsRefused() throws Exception {
        Context context = isolatedContext();
        OfflineBackupEvidence evidence = new OfflineBackupEvidence(context);
        File stage = evidence.create();
        try {
            assertTrue(stage.getName().matches("[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\\.bhlibackup"));
            try { OfflineBackupEvidence.owned(context,"../bhli_offline.db"); fail("path escape"); } catch (IllegalArgumentException expected) { }
            try (FileOutputStream output = new FileOutputStream(stage)) { output.write(new byte[]{1,2,3}); }
            evidence.sync(stage.getName());
            assertEquals(stage.getCanonicalFile(), OfflineBackupEvidence.owned(context,stage.getName()));
        } finally { assertTrue(stage.delete()); }
    }
    @Test public void markerIsBoundedAndCannotOverwritePendingOperation() throws Exception {
        Context context = isolatedContext();
        OfflineBackupEvidence evidence = new OfflineBackupEvidence(context);
        assertNull(evidence.readMarker());
        try {
            try { evidence.writeMarker(new byte[4097]); fail("oversize marker"); } catch (IllegalArgumentException expected) { }
            byte[] marker = "fictional-test-marker".getBytes(StandardCharsets.US_ASCII);
            evidence.writeMarker(marker);
            assertArrayEquals(marker,evidence.readMarker());
            try { evidence.writeMarker(marker); fail("pending marker overwritten"); } catch (IllegalStateException expected) { }
        } finally { evidence.clearMarker(); }
    }
}
