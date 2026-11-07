import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:bhli_audit/offline/backup_state.dart';
import 'package:bhli_audit/offline/backup_store.dart';
import 'package:bhli_audit/offline/schema.dart';

void main() {
  setUpAll(sqfliteFfiInit);
  late Database db;
  late BackupState candidate;
  setUp(() async {
    candidate = decodeBackupState(
      File('test/fixtures/backup/python-android-state.ndjson')
          .readAsBytesSync(),
      platform: 'android',
    );
    db = await databaseFactoryFfi.openDatabase(
      inMemoryDatabasePath,
      options: OpenDatabaseOptions(singleInstance: false),
    );
    await db.execute('PRAGMA foreign_keys=ON');
    for (final ddl in offlineV2Tables.values) {
      await db.execute(ddl);
    }
    await db.transaction(createOfflineIndexes);
    await db.execute('PRAGMA user_version=2');
    await db.insert('app_meta', {
      'key': 'app_id',
      'value': 'com.bhli.audit.offline',
    });
    await db.insert('app_meta', {
      'key': 'installation_id',
      'value': '00000000-0000-4000-8000-000000000001',
    });
    await db.execute('CREATE TABLE android_metadata (locale TEXT)');
    await db.insert('android_metadata', {'locale': 'en_PH'});
  });
  tearDown(() => db.close());
  test('captures empty complete owned state and absent sequence', () async {
    final state = await db.transaction(captureBackupTransaction);
    expect(state.rows.keys.toSet(), candidate.rows.keys.toSet());
    expect(state.sequence, isNull);
    expect(state.rows['local_profile'], isEmpty);
  });
  test('replaces every owned row and sequence atomically, preserving native metadata', () async {
    final original = await db.transaction(captureBackupTransaction);
    await db.transaction(
      (txn) => replaceBackupTransaction(txn, candidate, original.digest),
    );
    final restored = await db.transaction(captureBackupTransaction);
    expect(restored.digest, candidate.digest);
    expect(restored.rows, candidate.rows);
    expect(restored.sequence, 90);
    expect(await db.query('android_metadata'), [
      {'locale': 'en_PH'},
    ]);
    await db.transaction(
      (txn) => replaceBackupTransaction(txn, original, candidate.digest),
    );
    expect(
      (await db.transaction(captureBackupTransaction)).digest,
      original.digest,
    );
    expect(await db.query('sqlite_sequence'), isEmpty);
  });
  test(
    'same count changed identity invalidates preview before any deletion',
    () async {
      final original = await db.transaction(captureBackupTransaction);
      await db.update(
        'app_meta',
        {'value': '00000000-0000-4000-8000-000000000002'},
        where: 'key=?',
        whereArgs: ['installation_id'],
      );
      final changed = await db.transaction(captureBackupTransaction);
      await expectLater(
        db.transaction(
          (txn) => replaceBackupTransaction(txn, candidate, original.digest),
        ),
        throwsA(isA<BackupStoreFailure>()),
      );
      expect(
        (await db.transaction(captureBackupTransaction)).digest,
        changed.digest,
      );
    },
  );
  test('equal row counts with profile, raw history or sequence changes invalidate digest', () async {
    final original = await db.transaction(captureBackupTransaction);
    await db.transaction(
      (txn) => replaceBackupTransaction(txn, candidate, original.digest),
    );
    for (final statement in [
      "UPDATE local_profile SET name='Changed profile'",
      "UPDATE audit_events SET after_json=' ' || after_json || ' '",
      "UPDATE sqlite_sequence SET seq=91 WHERE name='audit_records'",
    ]) {
      final before = await db.transaction(captureBackupTransaction);
      await db.execute(statement);
      final changed = await db.transaction(captureBackupTransaction);
      expect(changed.digest, isNot(before.digest));
      for (final table in before.rows.keys) {
        expect(changed.rows[table]!.length, before.rows[table]!.length);
      }
      await expectLater(
        db.transaction(
          (txn) => replaceBackupTransaction(txn, original, before.digest),
        ),
        throwsA(isA<BackupStoreFailure>()),
      );
      expect(
        (await db.transaction(captureBackupTransaction)).digest,
        changed.digest,
      );
    }
  });
  test(
    'oversized stored row is rejected as a whole before capture payload',
    () async {
      await db.execute(
        "UPDATE app_meta SET value=printf('%.*c',1048577,65) WHERE key='installation_id'",
      );
      await expectLater(
        db.transaction(captureBackupTransaction),
        throwsA(isA<BackupStoreFailure>()),
      );
      expect(
        (await db.rawQuery(
          "SELECT length(value) AS n FROM app_meta WHERE key='installation_id'",
        )).single['n'],
        1048577,
      );
    },
  );
  test(
    'actual SQLite insertion fault rolls back complete replacement',
    () async {
      final original = await db.transaction(captureBackupTransaction);
      await db.execute(
        "CREATE TEMP TRIGGER injected BEFORE INSERT ON audit_records BEGIN SELECT RAISE(ABORT,'injected'); END",
      );
      await expectLater(
        db.transaction(
          (txn) => replaceBackupTransaction(txn, candidate, original.digest),
        ),
        throwsA(anything),
      );
      expect(
        (await db.transaction(captureBackupTransaction)).digest,
        original.digest,
      );
    },
  );
}
