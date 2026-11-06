import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:bhli_audit/offline/backup_state.dart';
import 'package:bhli_audit/offline/backup_sqlite.dart';

class ScratchFactory implements DatabaseFactory {
  ScratchFactory(this.path, {this.foreignSchema = false});
  final String path;
  final bool foreignSchema;
  Database? opened;
  int calls = 0;
  @override
  Future<Database> openDatabase(
    String path, {
    OpenDatabaseOptions? options,
  }) async {
    calls++;
    expect(path, inMemoryDatabasePath);
    expect(options!.singleInstance, isFalse);
    return opened = await databaseFactoryFfi.openDatabase(
      this.path,
      options: OpenDatabaseOptions(
        singleInstance: false,
        onConfigure: options.onConfigure,
        onOpen: (db) async {
          if (options.onOpen != null) await options.onOpen!(db);
          if (foreignSchema) {
            await db.execute('CREATE TABLE foreign_owned (id TEXT)');
          }
        },
      ),
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Uint8List golden() =>
    File('test/fixtures/backup/python-android-state.ndjson').readAsBytesSync();
void main() {
  setUpAll(sqfliteFfiInit);
  late Directory dir;
  setUp(
    () => dir = Directory.systemTemp.createTempSync('bhli-backup-scratch-'),
  );
  tearDown(() => dir.deleteSync(recursive: true));
  test('populated authenticated candidate passes fixed SQLite schema and exact row readback', () async {
    final factory = ScratchFactory('${dir.path}/scratch.db');
    final state = await inspectBackupSqlite(golden(), factory: factory);
    expect(
      state.digest,
      '143427275430e2fd11ef5fa3f395bf9f1ef9d597afba7fcf989ba899bf5fa08d',
    );
    expect(factory.calls, 1);
    expect(factory.opened!.isOpen, isFalse);
    final db = await databaseFactoryFfi.openDatabase(
      factory.path,
      options: OpenDatabaseOptions(singleInstance: false),
    );
    try {
      for (final table in state.rows.keys) {
        final actual = await db.query(table);
        expect(actual, unorderedEquals(state.rows[table]!));
      }
      expect(
        (await db.query(
          'sqlite_sequence',
          where: 'name = ?',
          whereArgs: ['audit_records'],
        )).single['seq'],
        90,
      );
      expect(
        (await db.rawQuery('PRAGMA user_version')).single.values.single,
        2,
      );
      expect(await db.rawQuery('PRAGMA foreign_key_check'), isEmpty);
      expect(
        (await db.rawQuery('PRAGMA integrity_check')).single.values.single,
        'ok',
      );
    } finally {
      await db.close();
    }
  });
  test(
    'fresh empty candidate retains absent sequence and no profile',
    () async {
      final original = decodeBackupState(golden(), platform: 'android');
      final rows = {
        for (final table in original.rows.keys)
          table: table == 'app_meta'
              ? original.rows[table]!
              : <Map<String, Object?>>[],
      };
      final payload = encodeBackupState(
        rows,
        platform: 'android',
        backupId: original.metadata['backup_id'] as String,
        createdAt: original.metadata['created_at'] as String,
        sourceVersion: 'fixture',
      );
      final factory = ScratchFactory('${dir.path}/scratch.db');
      final state = await inspectBackupSqlite(payload, factory: factory);
      expect(state.sequence, isNull);
      expect(state.rows['local_profile'], isEmpty);
      expect(factory.opened!.isOpen, isFalse);
      final db = await databaseFactoryFfi.openDatabase(factory.path);
      try {
        expect(await db.query('sqlite_sequence'), isEmpty);
      } finally {
        await db.close();
      }
    },
  );
  test('raw noncanonical history whitespace and timestamp spellings survive scratch insertion', () async {
    final original = decodeBackupState(golden(), platform: 'android');
    final rows = {
      for (final entry in original.rows.entries)
        entry.key: entry.value
            .map((r) => Map<String, Object?>.from(r))
            .toList(),
    };
    for (final event in rows['audit_events']!) {
      for (final key in ['before_json', 'after_json']) {
        if (event[key] is String) {
          event[key] = '  ${event[key]}  ';
        }
      }
    }
    final bytes = encodeBackupState(
      rows,
      platform: 'android',
      sequence: 90,
      backupId: original.metadata['backup_id'] as String,
      createdAt: original.metadata['created_at'] as String,
      sourceVersion: 'fixture',
    );
    final state = await inspectBackupSqlite(bytes, factory: databaseFactoryFfi);
    expect(state.rows, rows);
  });
  test('rejects broken references and column primitive types before opening scratch', () async {
    final text = utf8.decode(golden());
    for (final malformed in [
      text
          .replaceAll(
            '329410a4-8157-4dea-9bf4-ec8b97b93bdf',
            '00000000-0000-4000-8000-000000000000',
          )
          .replaceFirst(
            '"id":"00000000-0000-4000-8000-000000000000"',
            '"id":"329410a4-8157-4dea-9bf4-ec8b97b93bdf"',
          ),
      text.replaceFirst('"singleton":1', '"singleton":"1"'),
      text.replaceFirst('"schema_version":2', '"schema_version":3'),
    ]) {
      final factory = ScratchFactory('${dir.path}/scratch.db');
      await expectLater(
        inspectBackupSqlite(
          Uint8List.fromList(utf8.encode(malformed)),
          factory: factory,
        ),
        throwsFormatException,
      );
      expect(factory.calls, 0);
    }
  });
  test(
    'rejects unexpected scratch schema and always closes its connection',
    () async {
      final factory = ScratchFactory(
        '${dir.path}/scratch.db',
        foreignSchema: true,
      );
      await expectLater(
        inspectBackupSqlite(golden(), factory: factory),
        throwsFormatException,
      );
      expect(factory.opened!.isOpen, isFalse);
    },
  );
}
