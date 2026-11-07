import 'dart:isolate';
import 'dart:typed_data';

import 'package:sqflite/sqflite.dart';

import 'backup_state.dart';
import 'schema.dart';

// All identifiers below are built in. Payload keys are never SQL identifiers.
const _columns = <String, String>{
  'app_meta': 'key value',
  'local_profile': 'singleton id name',
  'auditor_identities': 'id',
  'audit_records': 'seq id profile_id driver_name helper_name audit_date station plate_number remarks audited_by_name created_at updated_at revision archived_at',
  'audit_events': 'id audit_id revision action actor_name actor_profile_id created_at before_json after_json',
  'transfer_receipts': 'package_id content_sha256 source_installation_id imported_at imported_count',
};
const _integers = {'singleton', 'seq', 'revision', 'imported_count'};
const _nullable = {'helper_name', 'remarks', 'archived_at', 'before_json'};
Never _bad() => throw const FormatException(
  'Invalid or unsupported complete backup state. Nothing was restored.',
);
void _need(bool value) {
  if (!value) _bad();
}

void _row(Map<String, Object?> row, List<String> columns) {
  _need(row.length == columns.length && columns.every(row.containsKey));
  for (final column in columns) {
    final value = row[column];
    _need(
      value == null
          ? _nullable.contains(column)
          : _integers.contains(column)
          ? value is int
          : value is String,
    );
  }
}

/// Validates already-authenticated Android payload in a fresh owned scratch DB.
/// This never opens the active store or executes schema supplied by a backup.
Future<BackupState> inspectBackupSqlite(
  Uint8List authenticatedPayload, {
  DatabaseFactory? factory,
}) async {
  _need(authenticatedPayload.length <= 64 * 1024 * 1024);
  final payload = Uint8List.fromList(authenticatedPayload);
  final state = await _decodeDetached(payload);
  Database? scratch;
  try {
    scratch = await (factory ?? databaseFactory).openDatabase(
      inMemoryDatabasePath,
      options: OpenDatabaseOptions(
        singleInstance: false,
        onConfigure: (db) async {
          await db.execute('PRAGMA foreign_keys = ON');
        },
      ),
    );
    await scratch.execute('PRAGMA foreign_keys = ON');
    _need(
      (await scratch.rawQuery('PRAGMA foreign_keys')).single.values.single == 1,
    );
    await scratch.transaction((txn) async {
      for (final table in _columns.keys) {
        await txn.execute(offlineV2Tables[table]!);
      }
      await createOfflineIndexes(txn);
      await txn.execute('PRAGMA user_version = 2');
      for (final entry in _columns.entries) {
        final columns = entry.value.split(' ');
        final sql =
            'INSERT INTO ${entry.key} (${columns.join(',')}) VALUES (${List.filled(columns.length, '?').join(',')})';
        for (final row in state.rows[entry.key]!) {
          _row(row, columns);
          await txn.rawInsert(sql, [for (final column in columns) row[column]]);
        }
      }
      await txn.delete(
        'sqlite_sequence',
        where: 'name = ?',
        whereArgs: ['audit_records'],
      );
      if (state.sequence != null) {
        await txn.rawInsert(
          'INSERT INTO sqlite_sequence (name,seq) VALUES (?,?)',
          ['audit_records', state.sequence],
        );
      }
      await verifyOfflineSchema(txn, 2);
      await validateOfflineRows(txn, 2);
      _need(
        (await txn.rawQuery('PRAGMA integrity_check')).single.values.single ==
            'ok',
      );
      _need((await txn.rawQuery('PRAGMA foreign_key_check')).isEmpty);
      _need(
        (await txn.rawQuery('PRAGMA foreign_keys')).single.values.single == 1,
      );
      _need(
        (await txn.rawQuery('PRAGMA user_version')).single.values.single == 2,
      );
      final readback = <String, List<Map<String, Object?>>>{};
      for (final table in _columns.keys) {
        final rows = await txn.query(
          table,
          columns: _columns[table]!.split(' '),
        );
        _need(rows.length == state.rows[table]!.length);
        readback[table] = rows;
      }
      final sequence = await txn.query(
        'sqlite_sequence',
        columns: ['seq'],
        where: 'name = ?',
        whereArgs: ['audit_records'],
      );
      _need(sequence.length == (state.sequence == null ? 0 : 1));
      if (sequence.isNotEmpty) _need(sequence.single['seq'] == state.sequence);
      // Revalidate complete SQLite readback, including raw JSON/timestamps, off UI.
      final verified = await _readbackDetached(
        readback,
        state.sequence,
        state.metadata,
      );
      _need(verified.digest == state.digest);
    });
    return state;
  } on Object {
    _bad();
  } finally {
    if (scratch != null) {
      try {
        await scratch.close();
      } on Object {
        _bad();
      }
    }
  }
}

// Keep native DB/Transaction values out of worker-isolate closure contexts.
Future<BackupState> _decodeDetached(Uint8List payload) =>
    Isolate.run(() => decodeBackupState(payload, platform: 'android'));
Future<BackupState> _readbackDetached(
  Map<String, List<Map<String, Object?>>> readback,
  int? sequence,
  Map<String, Object?> metadata,
) => Isolate.run(
  () => decodeBackupState(
    encodeBackupState(
      readback,
      platform: 'android',
      sequence: sequence,
      backupId: metadata['backup_id'] as String,
      createdAt: metadata['created_at'] as String,
      sourceVersion: metadata['source_version'] as String,
    ),
    platform: 'android',
  ),
);
