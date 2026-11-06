import 'dart:convert';

import 'package:sqflite/sqflite.dart';

import 'models.dart';

/// Owned SQL is deliberately fixed: an upgrade never repairs a foreign schema.
const offlineV1Tables = <String, String>{
  'app_meta': 'CREATE TABLE app_meta (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)',
  'local_profile': 'CREATE TABLE local_profile (singleton INTEGER PRIMARY KEY CHECK(singleton = 1), id TEXT UNIQUE NOT NULL, name TEXT NOT NULL)',
  'audit_records': 'CREATE TABLE audit_records (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, profile_id TEXT NOT NULL REFERENCES local_profile(id), driver_name TEXT NOT NULL, helper_name TEXT, audit_date TEXT NOT NULL, station TEXT NOT NULL, plate_number TEXT NOT NULL, remarks TEXT, audited_by_name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision >= 1), archived_at TEXT)',
  'audit_events': "CREATE TABLE audit_events (id TEXT PRIMARY KEY NOT NULL, audit_id TEXT NOT NULL REFERENCES audit_records(id), revision INTEGER NOT NULL CHECK(revision >= 1), action TEXT NOT NULL CHECK(action IN ('CREATE','UPDATE','ARCHIVE')), actor_name TEXT NOT NULL, actor_profile_id TEXT NOT NULL, created_at TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL, UNIQUE(audit_id, revision))",
};
final offlineV2Tables = <String, String>{
  ...offlineV1Tables,
  'auditor_identities':
      'CREATE TABLE auditor_identities (id TEXT PRIMARY KEY NOT NULL)',
  'audit_records': offlineV1Tables['audit_records']!.replaceFirst(
    'REFERENCES local_profile(id)',
    'REFERENCES auditor_identities(id)',
  ),
  'audit_events': offlineV1Tables['audit_events']!.replaceFirst(
    'actor_profile_id TEXT NOT NULL,',
    'actor_profile_id TEXT NOT NULL REFERENCES auditor_identities(id),',
  ),
  'transfer_receipts': 'CREATE TABLE transfer_receipts (package_id TEXT PRIMARY KEY NOT NULL, content_sha256 TEXT NOT NULL, source_installation_id TEXT NOT NULL, imported_at TEXT NOT NULL, imported_count INTEGER NOT NULL CHECK(imported_count>=0))',
};
const offlineIndexes = <String, String>{
  'audit_records_date':
      'CREATE INDEX audit_records_date ON audit_records(audit_date, seq)',
  'audit_records_archive':
      'CREATE INDEX audit_records_archive ON audit_records(archived_at, seq)',
  'audit_records_station':
      'CREATE INDEX audit_records_station ON audit_records(station, seq)',
};
const _schemaFailure = OfflineFailure(
  'schema',
  'This local database is not supported by this app.',
);
Never _bad() => throw _schemaFailure;

String _sql(String value) => value
    // SQLite adds these quotes when renaming replacement tables.
    .replaceAll('"audit_records"', 'audit_records')
    .replaceAll('"audit_events"', 'audit_events');

Future<void> verifyOfflineSchema(Transaction txn, int version) async {
  final expected = version == 1 ? offlineV1Tables : offlineV2Tables;
  final objects = await txn.rawQuery(
    "SELECT type,name,sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'",
  );
  final seen = <String>{};
  for (final object in objects) {
    final name = object['name'] as String;
    final type = object['type'];
    final sql = object['sql'];
    if (name == 'android_metadata' && type == 'table') {
      if (sql != 'CREATE TABLE android_metadata (locale TEXT)') _bad();
      continue;
    }
    final wanted = type == 'table'
        ? expected[name]
        : type == 'index'
        ? offlineIndexes[name]
        : null;
    if (wanted == null || sql is! String || _sql(sql) != wanted) _bad();
    seen.add(name);
  }
  if (seen.length != expected.length + offlineIndexes.length) _bad();
  final meta = await txn.query('app_meta');
  final values = {for (final row in meta) row['key']: row['value']};
  if (meta.length != 2 ||
      values['app_id'] != 'com.bhli.audit.offline' ||
      values['installation_id'] is! String ||
      !validOfflineUuid(values['installation_id'] as String)) {
    _bad();
  }
  final quick = await txn.rawQuery('PRAGMA quick_check');
  if (quick.length != 1 ||
      quick.single.values.single != 'ok' ||
      (await txn.rawQuery('PRAGMA foreign_key_check')).isNotEmpty) {
    _bad();
  }
}

bool _same(Object? a, Object? b) {
  if (a is Map && b is Map) {
    return a.length == b.length &&
        a.keys.every((key) => b.containsKey(key) && _same(a[key], b[key]));
  }
  return a == b;
}

void _uuid(Object? value) {
  if (value is! String || !validOfflineUuid(value)) _bad();
}

void _name(Object? value) {
  if (value is! String || offlineText(value, 200) != value) _bad();
}

DateTime _time(Object? value) {
  if (value is! String) _bad();
  final match = RegExp(
    r'^([1-9][0-9]{3}-[0-9]{2}-[0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]{1,6})?(Z|[+-]([0-9]{2}):([0-9]{2}))$',
  ).firstMatch(value);
  if (match == null ||
      !validOfflineDate(match.group(1)!) ||
      int.parse(match.group(2)!) > 23 ||
      int.parse(match.group(3)!) > 59 ||
      int.parse(match.group(4)!) > 59 ||
      (match.group(5) != 'Z' &&
          (int.parse(match.group(6)!) > 23 ||
              int.parse(match.group(7)!) > 59))) {
    _bad();
  }
  final parsed = DateTime.tryParse(value);
  if (parsed == null ||
      parsed.toUtc().year < 1000 ||
      parsed.toUtc().year > 9999) {
    _bad();
  }
  return parsed.toUtc();
}

const _fields = [
  'driver_name',
  'helper_name',
  'audit_date',
  'station',
  'plate_number',
  'remarks',
];
const _snapshotKeys = [
  'id',
  'profile_id',
  'audited_by_name',
  'created_at',
  'updated_at',
  'revision',
  'archived_at',
  ..._fields,
];
void _snapshot(Map<String, Object?> row) {
  if (row.length != _snapshotKeys.length ||
      !_snapshotKeys.every(row.containsKey)) {
    _bad();
  }
  _uuid(row['id']);
  _uuid(row['profile_id']);
  _name(row['audited_by_name']);
  final normalized = AuditValues.fromJson({
    for (final key in _fields) key: row[key],
  }).toJson();
  if (!_fields.every((key) => row[key] == normalized[key])) _bad();
  if (row['revision'] is! int || (row['revision'] as int) < 1) _bad();
  _time(row['created_at']);
  _time(row['updated_at']);
  if (row['archived_at'] != null) _time(row['archived_at']);
}

/// Validate historical values before writing anything. Clock reversal is valid.
Future<Set<String>> validateOfflineRows(Transaction txn, int version) async {
  try {
    final identities = <String>{};
    final profiles = await txn.query('local_profile');
    if (profiles.length > 1) _bad();
    for (final profile in profiles) {
      if (profile['singleton'] != 1) _bad();
      _uuid(profile['id']);
      _name(profile['name']);
      identities.add(profile['id'] as String);
    }
    final records = await txn.query('audit_records');
    var eventCount = 0;
    for (final row in records) {
      if (row['seq'] is! int || (row['seq'] as int) < 1) _bad();
      final current = Map<String, Object?>.from(row)..remove('seq');
      _snapshot(current);
      identities.add(row['profile_id'] as String);
      final events = await txn.query(
        'audit_events',
        where: 'audit_id = ?',
        whereArgs: [row['id']],
        orderBy: 'revision',
      );
      eventCount += events.length;
      if (events.length != row['revision']) _bad();
      Map<String, Object?>? previous;
      for (var i = 0; i < events.length; i++) {
        final event = events[i];
        _uuid(event['id']);
        _uuid(event['actor_profile_id']);
        _name(event['actor_name']);
        identities.add(event['actor_profile_id'] as String);
        final before = event['before_json'] == null
            ? null
            : jsonDecode(event['before_json'] as String);
        final after = Map<String, Object?>.from(
          jsonDecode(event['after_json'] as String) as Map,
        );
        _snapshot(after);
        if (!_same(before, previous) ||
            event['revision'] != i + 1 ||
            after['revision'] != i + 1 ||
            after['id'] != row['id'] ||
            _time(event['created_at']) != _time(after['updated_at'])) {
          _bad();
        }
        if (i == 0) {
          if (event['action'] != 'CREATE' ||
              after['archived_at'] != null ||
              _time(after['created_at']) != _time(after['updated_at']) ||
              event['actor_profile_id'] != after['profile_id'] ||
              event['actor_name'] != after['audited_by_name']) {
            _bad();
          }
        } else {
          if (previous!['archived_at'] != null ||
              ![
                'id',
                'profile_id',
                'audited_by_name',
                'created_at',
              ].every((key) => previous![key] == after[key])) {
            _bad();
          }
          if (event['action'] == 'ARCHIVE') {
            if (after['archived_at'] == null ||
                _time(after['archived_at']) != _time(after['updated_at']) ||
                !_fields.every((key) => previous![key] == after[key])) {
              _bad();
            }
          } else if (event['action'] != 'UPDATE' ||
              after['archived_at'] != null ||
              _fields.every((key) => previous![key] == after[key])) {
            _bad();
          }
        }
        previous = after;
      }
      if (!_same(previous, current)) _bad();
    }
    if ((await txn.rawQuery('SELECT COUNT(*) AS n FROM audit_events'))
            .single['n'] !=
        eventCount) {
      _bad();
    }
    if (version == 2) {
      final registry = await txn.query('auditor_identities');
      for (final identity in registry) {
        _uuid(identity['id']);
      }
      if (!registry.map((row) => row['id']).toSet().containsAll(identities)) {
        _bad();
      }
      for (final receipt in await txn.query('transfer_receipts')) {
        _uuid(receipt['package_id']);
        _uuid(receipt['source_installation_id']);
        _time(receipt['imported_at']);
        if (receipt['content_sha256'] is! String ||
            !RegExp(r'^[0-9a-f]{64}$')
                .hasMatch(receipt['content_sha256'] as String) ||
            receipt['imported_count'] is! int ||
            (receipt['imported_count'] as int) < 0) {
          _bad();
        }
      }
    }
    return identities;
  } on OfflineFailure {
    _bad();
  } on FormatException {
    _bad();
  } on TypeError {
    _bad();
  }
}

Future<void> createOfflineIndexes(Transaction txn) async {
  for (final sql in offlineIndexes.values) {
    await txn.execute(sql);
  }
}

/// The caller owns the transaction, including its final COMMIT and rollback.
Future<void> migrateOfflineV1(Transaction txn, Set<String> identities) async {
  final sequence = await txn.query(
    'sqlite_sequence',
    where: 'name = ?',
    whereArgs: ['audit_records'],
  );
  await txn.execute(offlineV2Tables['auditor_identities']!);
  for (final id in identities) {
    await txn.insert('auditor_identities', {'id': id});
  }
  await txn.execute(offlineV2Tables['transfer_receipts']!);
  await txn.execute(
    offlineV2Tables['audit_records']!.replaceFirst(
      'CREATE TABLE audit_records ',
      'CREATE TABLE audit_records_v2 ',
    ),
  );
  await txn.execute(
    offlineV2Tables['audit_events']!
        .replaceFirst(
          'CREATE TABLE audit_events ',
          'CREATE TABLE audit_events_v2 ',
        )
        .replaceFirst(
          'REFERENCES audit_records(id)',
          'REFERENCES audit_records_v2(id)',
        ),
  );
  for (final name in ['audit_records', 'audit_events']) {
    await txn.execute('INSERT INTO ${name}_v2 SELECT * FROM $name');
    final oldCount = (await txn.rawQuery('SELECT COUNT(*) AS n FROM $name'))
        .single['n'];
    if ((await txn.rawQuery('SELECT COUNT(*) AS n FROM ${name}_v2'))
            .single['n'] !=
        oldCount) {
      _bad();
    }
  }
  if ((await txn.rawQuery('PRAGMA foreign_key_check')).isNotEmpty) _bad();
  await txn.execute('DROP TABLE audit_events');
  await txn.execute('DROP TABLE audit_records');
  await txn.execute('ALTER TABLE audit_records_v2 RENAME TO audit_records');
  await txn.execute('ALTER TABLE audit_events_v2 RENAME TO audit_events');
  if (sequence.isNotEmpty) {
    await txn.update(
      'sqlite_sequence',
      {'seq': sequence.single['seq']},
      where: 'name = ?',
      whereArgs: ['audit_records'],
    );
  }
  await createOfflineIndexes(txn);
  await verifyOfflineSchema(txn, 2);
  await txn.execute('PRAGMA user_version = 2');
}
