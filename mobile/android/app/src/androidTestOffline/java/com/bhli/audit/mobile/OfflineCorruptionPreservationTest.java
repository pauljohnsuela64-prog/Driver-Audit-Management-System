package com.bhli.audit.mobile;

import static org.junit.Assert.*;
import android.content.Context;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.database.sqlite.SQLiteDatabase;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.io.FileOutputStream;
import java.io.RandomAccessFile;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.io.FileInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Arrays;
import java.util.UUID;
import java.util.Map;
import java.util.List;
import java.util.ArrayList;
import java.lang.reflect.Proxy;
import java.security.MessageDigest;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

/** Safety reproduction against the exact pinned plugin, only generated cache fixtures. */
public final class OfflineCorruptionPreservationTest {
    private Context context() { return InstrumentationRegistry.getInstrumentation().getTargetContext(); }
    private File fixture(String name) throws Exception {
        File root=new File(context().getCacheDir(),"corruption-probe-"+UUID.randomUUID()).getCanonicalFile();
        assertTrue(root.mkdir()); return new File(root,name);
    }
    private byte[] corruptBytes() {
        byte[] bytes=new byte[4096]; Arrays.fill(bytes,(byte)0x41);
        byte[] label="FICTIONAL CORRUPT SQLITE FIXTURE ONLY".getBytes(StandardCharsets.US_ASCII);
        System.arraycopy(label,0,bytes,0,label.length); return bytes;
    }
    private void write(File file,byte[] bytes) throws Exception {
        try(FileOutputStream output=new FileOutputStream(file)) { output.write(bytes); output.flush(); output.getFD().sync(); }
    }
    private byte[] read(File file) throws Exception {
        try(FileInputStream input=new FileInputStream(file); ByteArrayOutputStream output=new ByteArrayOutputStream()) {
            byte[] buffer=new byte[8192]; int count;
            while((count=input.read(buffer))!=-1) { assertTrue(output.size()+count<=1024*1024); output.write(buffer,0,count); }
            return output.toByteArray();
        }
    }
    private void evidence(File database,String phase,boolean copy) throws Exception {
        JSONArray files=new JSONArray();
        for(String suffix:new String[]{"","-wal","-shm","-journal"}) {
            File file=new File(database.getPath()+suffix);
            JSONObject entry=new JSONObject().put("path",file.getCanonicalPath()).put("exists",file.exists());
            if(file.exists()) {
                byte[] bytes=read(file); StringBuilder digest=new StringBuilder();
                for(byte value:MessageDigest.getInstance("SHA-256").digest(bytes)) digest.append(String.format("%02x",value & 255));
                entry.put("bytes",bytes.length).put("sha256",digest.toString());
                if(copy) write(new File(database.getParentFile(),"original-"+file.getName()+".fixture"),bytes);
            }
            files.put(entry);
        }
        write(new File(database.getParentFile(),phase+".json"),new JSONObject()
            .put("fictional_only",true).put("phase",phase).put("files",files)
            .toString(2).getBytes(StandardCharsets.UTF_8));
    }
    private void assertOriginalEvidence(File file) throws Exception {
        JSONObject before=new JSONObject(new String(read(new File(file.getParentFile(),"before.json")),StandardCharsets.UTF_8));
        JSONArray entries=before.getJSONArray("files");
        for(int index=0;index<entries.length();index++) {
            JSONObject entry=entries.getJSONObject(index);
            if(!entry.getBoolean("exists")) continue;
            File original=new File(entry.getString("path"));
            assertTrue("Damaged original or sidecar lost after close: "+original.getName(),original.exists());
            assertArrayEquals("Damaged original or sidecar modified after close: "+original.getName(),
                read(new File(file.getParentFile(),"original-"+original.getName()+".fixture")),read(original));
        }
    }
    private Object pinned(File file) throws Exception {
        Class<?> type=Class.forName("com.tekartik.sqflite.Database");
        Constructor<?> constructor=type.getDeclaredConstructor(Context.class,String.class,int.class,boolean.class,int.class);
        constructor.setAccessible(true); return constructor.newInstance(context(),file.getPath(),719,false,0);
    }
    private SQLiteDatabase connection(Object database) throws Exception {
        Field field=database.getClass().getDeclaredField("sqliteDatabase"); field.setAccessible(true);
        return (SQLiteDatabase)field.get(database);
    }
    private void open(Object database,boolean readOnly) throws Exception {
        Method method=database.getClass().getDeclaredMethod(readOnly ? "openReadOnly":"open");
        method.setAccessible(true); method.invoke(database);
    }
    private void assertBlocked(Object database) throws Exception {
        for(String name:new String[]{"getWritableDatabase","getReadableDatabase"}) {
            Method method=database.getClass().getDeclaredMethod(name); method.setAccessible(true);
            try {
                Object returned=method.invoke(database);
                // A failed native open may never assign a connection. Null is
                // refusal, not usable database access; runtime latches still
                // must reject any live connection.
                assertTrue("Corrupt connection still admits "+name,
                    returned==null || !((SQLiteDatabase)returned).isOpen());
            }
            catch(java.lang.reflect.InvocationTargetException expected) {
                assertTrue("Corruption must be distinguishable without exposing data",
                    expected.getCause().getMessage().contains("BHLI_OFFLINE_CORRUPTION"));
            }
        }
    }
    private void close(Object database) {
        try { SQLiteDatabase db=connection(database); if(db!=null && db.isOpen()) db.close(); } catch(Exception ignored) { }
    }
    private boolean pluginRefusesIntegrityQuery(Object database,boolean allowReadOnlyRecovery) throws Exception {
        List<String> errors=new ArrayList<>();
        Class<?> operationType=Class.forName("com.tekartik.sqflite.operation.Operation");
        Object operation=Proxy.newProxyInstance(operationType.getClassLoader(),new Class<?>[]{operationType},(proxy,method,args)-> {
            switch(method.getName()) {
                case "getSqlCommand": return new com.tekartik.sqflite.SqlCommand("PRAGMA integrity_check(1)",java.util.Collections.emptyList());
                case "getMethod": return "query";
                case "error": errors.add(String.valueOf(args[1])); return null;
                default: return method.getReturnType()==boolean.class ? false : null;
            }
        });
        Method query=database.getClass().getDeclaredMethod("query",operationType); query.setAccessible(true);
        query.invoke(database,operation);
        if(errors.isEmpty()) return false;
        assertEquals(1,errors.size());
        assertTrue("Startup query refusal was not classified: "+errors,
            errors.get(0).contains("BHLI_OFFLINE_CORRUPTION") ||
            (allowReadOnlyRecovery && errors.get(0).contains("SQLITE_READONLY_ROLLBACK")));
        return true;
    }
    private void startup(boolean readOnly) throws Exception {
        File file=fixture(readOnly ? "readonly.db":"writable.db"); byte[] original=corruptBytes(); write(file,original);
        String[] suffixes={"-wal","-shm","-journal"};
        byte[] sidecar="FICTIONAL PRESERVE SIDECAR".getBytes(StandardCharsets.US_ASCII);
        for(String suffix:suffixes) write(new File(file.getPath()+suffix),sidecar);
        evidence(file,"before",true);
        Object database=pinned(file);
        boolean refused=false;
        try {
            try { open(database,readOnly);
                // The application issues startup queries through sqflite. A
                // raw Android query bypasses the wrapper's NOTADB fallback.
                refused=pluginRefusesIntegrityQuery(database,readOnly);
            } catch(Exception expectedCorruption) { refused=true; }
        } finally { close(database); evidence(file,"after",false); }
        assertTrue("Original corrupt database was deleted by native open",file.exists());
        assertArrayEquals("Original corrupt database was rewritten/reset",original,read(file));
        // The operator's simplified contract permits native writable-open
        // sidecar cleanup. Keep its before/after evidence; require unchanged
        // main bytes and refusal rather than claiming forensic WAL preservation.
        if(readOnly) for(String suffix:suffixes) {
            File preserved=new File(file.getPath()+suffix);
            assertTrue("Read-only sidecar deleted: "+suffix,preserved.exists());
            assertArrayEquals("Read-only sidecar changed: "+suffix,sidecar,read(preserved));
        }
        assertTrue("Corrupt startup must refuse ordinary database access",refused);
        if(readOnly && !new File(file.getPath()+".bhli-corrupt").exists()) {
            // READONLY_ROLLBACK requires writable journal recovery first. The
            // actual guarded startup must then reject the damaged main, not
            // reset it. Sidecar cleanup remains documented normal SQLite work.
            Object recovery=pinned(file); boolean recoveryRefused=false;
            try { open(recovery,false); recoveryRefused=pluginRefusesIntegrityQuery(recovery,false); }
            catch(java.lang.reflect.InvocationTargetException expected) { recoveryRefused=true; }
            finally { close(recovery); evidence(file,"after-guarded-recovery-refusal",false); }
            assertTrue("Guarded writable recovery accepted the damaged main",recoveryRefused);
            assertArrayEquals("Guarded recovery reset the damaged main",original,read(file));
        }
        assertBlocked(database);
        assertRestartRefused(file);
    }
    private void assertRestartRefused(File file) throws Exception {
        assertTrue("Corruption flag must survive a new connection",new File(file.getPath()+".bhli-corrupt").exists());
        Object restarted=pinned(file);
        try { open(restarted,false); fail("A new connection silently reopened flagged storage"); }
        catch(java.lang.reflect.InvocationTargetException expected) {
            assertTrue(expected.getCause().getMessage().contains("BHLI_OFFLINE_CORRUPTION"));
        } finally { close(restarted); }
    }
    @Test public void pinnedWritableStartupMustPreserveCorruptOriginalAndSidecars() throws Exception { startup(false); }
    @Test public void pinnedReadOnlyStartupPreservesCorruptOriginalAndSidecars() throws Exception { startup(true); }
    @Test public void pinnedWritableRuntimeCorruptionMustNotDeleteOriginal() throws Exception { runtime(false); }
    @Test public void pinnedWalCorruptionRefusesUseWithoutDeletingOrResettingMain() throws Exception { runtime(true); }
    private void runtime(boolean wal) throws Exception {
        File file=fixture("runtime.db");
        SQLiteDatabase seed=SQLiteDatabase.openOrCreateDatabase(file,null);
        try { seed.execSQL("CREATE TABLE fictional (id INTEGER PRIMARY KEY,value TEXT)"); seed.execSQL("INSERT INTO fictional VALUES (1,'FICTIONAL ONLY')"); }
        finally { seed.close(); }
        Object database=pinned(file);
        try {
            open(database,false);
            SQLiteDatabase db=connection(database);
            if(wal) {
                assertTrue(db.enableWriteAheadLogging());
                // Genuine live WAL/SHM for an unrelated committed table. The
                // corrupted fictional table remains on its original main page.
                db.execSQL("CREATE TABLE unrelated_fictional (value TEXT)");
                db.execSQL("INSERT INTO unrelated_fictional VALUES ('FICTIONAL WAL ONLY')");
                assertTrue(new File(file.getPath()+"-wal").exists());
                assertTrue(new File(file.getPath()+"-shm").exists());
            }
            int pageSize,rootPage;
            try(Cursor cursor=db.rawQuery("PRAGMA page_size",null)) { assertTrue(cursor.moveToFirst()); pageSize=cursor.getInt(0); }
            try(Cursor cursor=db.rawQuery("SELECT rootpage FROM sqlite_master WHERE name='fictional'",null)) { assertTrue(cursor.moveToFirst()); rootPage=cursor.getInt(0); }
            db.execSQL("PRAGMA shrink_memory");
            try(RandomAccessFile damaged=new RandomAccessFile(file,"rw")) { damaged.seek((long)(rootPage-1)*pageSize); damaged.writeByte(0); damaged.getFD().sync(); }
            byte[] damaged=read(file);
            evidence(file,"before",true);
            boolean refused=false;
            try { try(Cursor cursor=db.rawQuery("SELECT * FROM fictional",null)) { cursor.moveToFirst(); } }
            catch(Exception expectedCorruption) { refused=true; }
            evidence(file,"after",false);
            assertTrue("Native runtime corruption handler deleted original",file.exists());
            assertArrayEquals("Native runtime corruption handler changed original",damaged,read(file));
            assertTrue("Corrupt query must fail",refused);
            assertBlocked(database);
        } finally { close(database); evidence(file,"closed",false); }
        if(!wal) assertOriginalEvidence(file);
        assertTrue("Corrupt main must not be deleted on close",file.exists());
        // A normal WAL checkpoint may change main bytes and remove sidecars.
        // It must not turn the damaged database into a fresh empty database.
        try(SQLiteDatabase inspection=SQLiteDatabase.openDatabase(file.getPath(),null,SQLiteDatabase.OPEN_READONLY,
            ignored -> { throw new android.database.sqlite.SQLiteDatabaseCorruptException("FICTIONAL inspection refused"); });
            Cursor tables=inspection.rawQuery("SELECT name FROM sqlite_master WHERE type='table' AND name='fictional'",null)) {
            assertTrue("Main was silently reset to an empty database",tables.moveToFirst());
        }
        assertRestartRefused(file);
    }

    @Test public void ordinaryFreshAndHealthyNativeDatabaseStillPersists() throws Exception {
        File file=fixture("healthy.db"); Object first=pinned(file);
        open(first,false);
        try(Cursor version=connection(first).rawQuery("SELECT sqlite_version()",null)) {
            assertTrue(version.moveToFirst());
            write(new File(file.getParentFile(),"native-environment.json"),new JSONObject()
                .put("android_api",android.os.Build.VERSION.SDK_INT)
                .put("sqlite_version",version.getString(0)).put("sqflite_android","2.4.5")
                .put("fictional_only",true).toString(2).getBytes(StandardCharsets.UTF_8));
        }
        try { connection(first).execSQL("CREATE TABLE fictional (value TEXT)"); connection(first).execSQL("INSERT INTO fictional VALUES ('Fictional healthy record')"); }
        finally { close(first); }
        Object second=pinned(file); open(second,false);
        try(Cursor cursor=connection(second).rawQuery("SELECT value FROM fictional",null)) {
            assertTrue(cursor.moveToFirst()); assertEquals("Fictional healthy record",cursor.getString(0));
        } finally { close(second); }
        assertFalse(new File(file.getPath()+".bhli-corrupt").exists());
    }

    @Test public void failedFlagWriteStillLatchesCurrentConnection() throws Exception {
        File file=fixture("flag-write-failure.db"); Object database=pinned(file); open(database,false);
        assertTrue(new File(file.getPath()+".bhli-corrupt").mkdir());
        Method handler=database.getClass().getDeclaredMethod("preservingErrorHandler"); handler.setAccessible(true);
        try { ((android.database.DatabaseErrorHandler)handler.invoke(database)).onCorruption(connection(database)); fail("Corruption must throw even if flag writing fails"); }
        catch(android.database.sqlite.SQLiteDatabaseCorruptException expected) { assertTrue(expected.getMessage().contains("BHLI_OFFLINE_CORRUPTION")); }
        try { assertBlocked(database); } finally { close(database); }
        assertTrue(file.exists()); assertRestartRefused(file);
    }

    @Test public void corruptCommitRefusesCleanupWithoutPlatformCallback() throws Exception {
        com.tekartik.sqflite.CorruptCommitProbe.verify(context(),fixture("commit.db").getPath());
    }
    @Test public void queuedCursorChecksPersistedCorruptionFlag() throws Exception { queuedCursor(true); }
    @Test public void queuedCursorCannotReturnCachedRowsAfterCorruptionLatch() throws Exception { queuedCursor(false); }
    @SuppressWarnings("unchecked") private void queuedCursor(boolean persistedFlag) throws Exception {
        File file=fixture("queued.db"); Object database=pinned(file);
        Class<?> type=database.getClass();
        MatrixCursor cursor=new MatrixCursor(new String[]{"fictional"});
        cursor.addRow(new Object[]{"MUST NOT RETURN AFTER CORRUPTION"});
        Class<?> holder=Class.forName("com.tekartik.sqflite.SqfliteCursor");
        Constructor<?> constructor=holder.getDeclaredConstructor(int.class,int.class,Cursor.class);
        constructor.setAccessible(true);
        Field cursors=type.getDeclaredField("cursors"); cursors.setAccessible(true);
        ((Map<Integer,Object>)cursors.get(database)).put(1,constructor.newInstance(1,1,cursor));
        Field transaction=type.getDeclaredField("currentTransactionId"); transaction.setAccessible(true); transaction.set(database,10);
        List<String> callbacks=new ArrayList<>();
        Class<?> operationType=Class.forName("com.tekartik.sqflite.operation.Operation");
        Object operation=Proxy.newProxyInstance(operationType.getClassLoader(),new Class<?>[]{operationType},(proxy,method,args)-> {
            switch(method.getName()) {
                case "getTransactionId": return 11;
                case "getArgument": return "cursorId".equals(args[0]) ? 1 : null;
                case "success": callbacks.add("success"); return null;
                case "error": callbacks.add(String.valueOf(args[1])); return null;
                case "getMethod": return "queryCursorNext";
                default: return method.getReturnType()==boolean.class ? false : null;
            }
        });
        Method next=type.getDeclaredMethod("queryCursorNext",operationType); next.setAccessible(true); next.invoke(database,operation);
        assertTrue(callbacks.isEmpty());
        if(persistedFlag) write(new File(file.getPath()+".bhli-corrupt"),new byte[]{1});
        else { Field latch=type.getDeclaredField("offlineCorruptionDetected"); latch.setAccessible(true); latch.set(database,true); }
        Method drain=type.getDeclaredMethod("runQueuedOperations"); drain.setAccessible(true); drain.invoke(database);
        assertEquals(1,callbacks.size());
        assertTrue("Queued cursor exposed data after corruption: "+callbacks,callbacks.get(0).contains("BHLI_OFFLINE_CORRUPTION"));
        cursor.close();
    }
}
