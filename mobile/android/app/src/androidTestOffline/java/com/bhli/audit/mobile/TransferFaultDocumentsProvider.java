package com.bhli.audit.mobile;

import android.database.Cursor;
import android.database.MatrixCursor;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.os.ParcelFileDescriptor;
import android.provider.DocumentsContract;
import android.content.ContentProvider;
import android.content.ContentValues;
import android.net.Uri;
import java.io.FileNotFoundException;

/** Virtual document protocol for fault injection; not a system URI-grant test. No files. */
public final class TransferFaultDocumentsProvider extends ContentProvider {
    public static final String AUTHORITY = "com.bhli.audit.offline.test.transferfault";
    private int existingDeletes, newDeletes, opens;
    private boolean failDelete;
    @Override public boolean onCreate() { return true; }
    @Override public synchronized Bundle call(String method, String arg, Bundle extras) {
        if ("reset".equals(method)) {
            existingDeletes = newDeletes = opens = 0;
            failDelete = extras != null && extras.getBoolean("failDelete");
            return new Bundle();
        }
        if ("counts".equals(method)) {
            Bundle result = new Bundle();
            result.putInt("existingDeletes", existingDeletes);
            result.putInt("newDeletes", newDeletes);
            result.putInt("opens", opens);
            return result;
        }
        if ("android:deleteDocument".equals(method)) {
            Uri uri = extras == null ? null : extras.getParcelable("uri");
            if (uri == null) throw new IllegalArgumentException("Missing fictional URI");
            try { deleteDocument(DocumentsContract.getDocumentId(uri)); }
            catch (FileNotFoundException failure) { throw new IllegalStateException(failure); }
            return new Bundle();
        }
        return super.call(method, arg, extras);
    }
    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        return openDocument(DocumentsContract.getDocumentId(uri), mode, null);
    }
    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) {
        try { return queryDocument(DocumentsContract.getDocumentId(uri), projection); }
        catch (FileNotFoundException failure) { throw new IllegalArgumentException(failure); }
    }
    @Override public String getType(Uri uri) { return "application/octet-stream"; }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri uri, ContentValues values, String where, String[] args) { throw new UnsupportedOperationException(); }
    @Override public int delete(Uri uri, String where, String[] args) { throw new UnsupportedOperationException(); }
    private void known(String id) throws FileNotFoundException {
        if (!"new".equals(id) && !"existing".equals(id)) throw new FileNotFoundException("Unknown fictional ID");
    }
    public synchronized ParcelFileDescriptor openDocument(String id, String mode,
            CancellationSignal signal) throws FileNotFoundException {
        known(id); opens++;
        throw new FileNotFoundException("Injected fictional transport failure");
    }
    public synchronized void deleteDocument(String id) throws FileNotFoundException {
        known(id);
        if ("existing".equals(id)) existingDeletes++; else newDeletes++;
        if (failDelete) throw new FileNotFoundException("Injected fictional cleanup failure");
    }
    public Cursor queryRoots(String[] projection) {
        return new MatrixCursor(projection != null ? projection : new String[]{DocumentsContract.Root.COLUMN_ROOT_ID});
    }
    public Cursor queryChildDocuments(String parent, String[] projection, String sort) {
        return new MatrixCursor(projection != null ? projection : new String[]{DocumentsContract.Document.COLUMN_DOCUMENT_ID});
    }
    public Cursor queryDocument(String id, String[] projection) throws FileNotFoundException {
        known(id);
        String[] columns = projection != null ? projection : new String[]{
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
            DocumentsContract.Document.COLUMN_FLAGS};
        MatrixCursor cursor = new MatrixCursor(columns);
        MatrixCursor.RowBuilder row = cursor.newRow();
        for (String column : columns) {
            if (DocumentsContract.Document.COLUMN_DOCUMENT_ID.equals(column)) row.add(id);
            else if (DocumentsContract.Document.COLUMN_DISPLAY_NAME.equals(column)) row.add("fictional-" + id + ".bhlitransfer");
            else if (DocumentsContract.Document.COLUMN_MIME_TYPE.equals(column)) row.add("application/octet-stream");
            else if (DocumentsContract.Document.COLUMN_FLAGS.equals(column)) row.add(DocumentsContract.Document.FLAG_SUPPORTS_DELETE | DocumentsContract.Document.FLAG_SUPPORTS_WRITE);
            else row.add(null);
        }
        return cursor;
    }
}
