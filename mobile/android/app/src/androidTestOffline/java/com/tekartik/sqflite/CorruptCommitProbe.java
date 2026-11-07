package com.tekartik.sqflite;

import static org.junit.Assert.*;
import android.content.Context;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteDatabaseCorruptException;
import com.tekartik.sqflite.operation.Operation;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Collections;
import java.util.ArrayList;
import java.util.List;

/** Test-only fault at the native connection seam, never included in the app. */
public final class CorruptCommitProbe {
    private static final class FaultDatabase extends Database {
        int accesses;
        FaultDatabase(Context context,String path) { super(context,path,927,false,0); }
        @Override public SQLiteDatabase getWritableDatabase() {
            accesses++;
            if(accesses==1) throw new SQLiteDatabaseCorruptException("Fictional commit corruption without callback");
            return super.getWritableDatabase();
        }
    }
    public static void verify(Context context,String path) throws Exception {
        FaultDatabase database=new FaultDatabase(context,path);
        List<String> results=new ArrayList<>();
        Operation operation=(Operation)Proxy.newProxyInstance(Operation.class.getClassLoader(),new Class<?>[]{Operation.class},(proxy,method,args)-> {
            switch(method.getName()) {
                case "getSqlCommand": return new SqlCommand("COMMIT",Collections.emptyList());
                case "getInTransactionChange": return false;
                case "error": results.add(String.valueOf(args[1])); return null;
                default: return method.getReturnType()==boolean.class ? false : null;
            }
        });
        Method execute=Database.class.getDeclaredMethod("executeOrError",Operation.class); execute.setAccessible(true);
        assertEquals(false,execute.invoke(database,operation));
        assertEquals("No further connection access after known corruption",1,database.accesses);
        assertEquals(1,results.size());
        assertTrue(results.get(0).contains("BHLI_OFFLINE_CORRUPTION"));
    }
}
