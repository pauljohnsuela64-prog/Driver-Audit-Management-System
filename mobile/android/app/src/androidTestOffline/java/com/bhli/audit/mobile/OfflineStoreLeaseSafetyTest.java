package com.bhli.audit.mobile;

import static org.junit.Assert.*;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.util.UUID;
import org.junit.Test;

public class OfflineStoreLeaseSafetyTest {
    @Test public void competingOwnerAndStaleTokenCannotReleaseLease() throws Exception {
        File dir = new File(InstrumentationRegistry.getInstrumentation().getTargetContext().getCacheDir(), "lease-test-" + UUID.randomUUID()).getCanonicalFile();
        assertTrue(dir.mkdir());
        String first = OfflineStoreLease.acquire(dir);
        try {
            try { OfflineStoreLease.acquire(dir); fail("second owner admitted"); } catch (IllegalStateException expected) { }
            try { OfflineStoreLease.release("stale"); fail("stale release admitted"); } catch (IllegalStateException expected) { }
            OfflineStoreLease.ensureHeld(first);
        } finally { OfflineStoreLease.release(first); }
        String second = OfflineStoreLease.acquire(dir);
        try {
            assertNotEquals(first, second);
            try { OfflineStoreLease.release(first); fail("old owner released new lease"); } catch (IllegalStateException expected) { }
            OfflineStoreLease.ensureHeld(second);
        } finally { OfflineStoreLease.release(second); }
        assertTrue(new File(dir,"offline-store.owner.lock").exists());
    }
}
