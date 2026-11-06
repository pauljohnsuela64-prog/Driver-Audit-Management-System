package com.bhli.audit.mobile;

import android.app.Activity;
import android.content.Context;
import java.io.File;
import java.util.UUID;

/** Plain context-bound Activity: no Flutter engine or production navigation. */
public final class TransferDocumentsTestActivity extends Activity {
    private File ownedFiles;
    public void bind(Context context) {
        attachBaseContext(context);
        ownedFiles = new File(context.getFilesDir(), "acceptance6d-native-" + UUID.randomUUID());
        if (!ownedFiles.mkdir()) throw new AssertionError("Cannot create unique native test directory");
    }
    @Override public File getFilesDir() { return ownedFiles; }
}
