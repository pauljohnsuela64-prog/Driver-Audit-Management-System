import 'dart:convert';
import 'dart:io';

import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/sqlite_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

const profileId = '11111111-1111-4111-8111-111111111111';
const auditId = '22222222-2222-4222-8222-222222222222';
const eventId = '33333333-3333-4333-8333-333333333333';
const installationId = '44444444-4444-4444-8444-444444444444';
const actorId = '55555555-5555-4555-8555-555555555555';

// Independent historical DDL: weakening a constraint or losing a snapshot
// must be detected even when the repository's current schema changes.
const v1Tables = [
  'CREATE TABLE app_meta (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)',
  'CREATE TABLE local_profile (singleton INTEGER PRIMARY KEY CHECK(singleton = 1), id TEXT UNIQUE NOT NULL, name TEXT NOT NULL)',
  'CREATE TABLE audit_records (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, profile_id TEXT NOT NULL REFERENCES local_profile(id), driver_name TEXT NOT NULL, helper_name TEXT, audit_date TEXT NOT NULL, station TEXT NOT NULL, plate_number TEXT NOT NULL, remarks TEXT, audited_by_name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision >= 1), archived_at TEXT)',
  "CREATE TABLE audit_events (id TEXT PRIMARY KEY NOT NULL, audit_id TEXT NOT NULL REFERENCES audit_records(id), revision INTEGER NOT NULL CHECK(revision >= 1), action TEXT NOT NULL CHECK(action IN ('CREATE','UPDATE','ARCHIVE')), actor_name TEXT NOT NULL, actor_profile_id TEXT NOT NULL, created_at TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL, UNIQUE(audit_id, revision))",
];
const v1Indexes = [
  'CREATE INDEX audit_records_date ON audit_records(audit_date, seq)',
  'CREATE INDEX audit_records_archive ON audit_records(archived_at, seq)',
  'CREATE INDEX audit_records_station ON audit_records(station, seq)',
];

// The wrapper injects a real deferred SQLite constraint after migration work;
// SQLite itself rejects COMMIT, exercising the repository's rollback path.
class CommitFaultDatabase extends Database {
  CommitFaultDatabase(this.delegate);
  final Database delegate;
  @override
  Future<T> transaction<T>(
    Future<T> Function(Transaction) action, {
    bool? exclusive,
  }) => delegate.transaction((txn) async {
    final result = await action(txn);
    await txn.execute(
      'CREATE TABLE migration_fault_parent(id INTEGER PRIMARY KEY)',
    );
    await txn.execute(
      'CREATE TABLE migration_fault_child(id INTEGER REFERENCES migration_fault_parent(id) DEFERRABLE INITIALLY DEFERRED)',
    );
    await txn.insert('migration_fault_child', {'id': 9});
    return result;
  }, exclusive: exclusive);
  @override
  Future<void> close() => delegate.close();
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class CommitFaultFactory extends DatabaseFactory {
  @override
  Future<Database> openDatabase(
    String path, {
    OpenDatabaseOptions? options,
  }) async => CommitFaultDatabase(
    await databaseFactoryFfi.openDatabase(path, options: options),
  );
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<Database> fixture(String path, {String? alteredTable}) async {
  final db = await databaseFactoryFfi.openDatabase(
    path,
    options: OpenDatabaseOptions(singleInstance: false),
  );
  await db.execute('PRAGMA foreign_keys = ON');
  for (var i = 0; i < v1Tables.length; i++) {
    await db.execute(
      i == 3 && alteredTable != null ? alteredTable : v1Tables[i],
    );
  }
  for (final sql in v1Indexes) {
    await db.execute(sql);
  }
  await db.insert('app_meta', {
    'key': 'app_id',
    'value': 'com.bhli.audit.offline',
  });
  await db.insert('app_meta', {
    'key': 'installation_id',
    'value': installationId,
  });
  await db.insert('local_profile', {
    'singleton': 1,
    'id': profileId,
    'name': 'Renamed Auditor',
  });
  final first = <String, Object?>{
    'id': auditId,
    'profile_id': profileId,
    'driver_name': 'Fictional Driver',
    'helper_name': null,
    'audit_date': '2026-11-05',
    'station': 'North',
    'plate_number': '00047',
    'remarks': null,
    'audited_by_name': 'Original Auditor',
    'created_at': '2026-11-05T12:00:00.000Z',
    'updated_at': '2026-11-05T12:00:00.000Z',
    'revision': 1,
    'archived_at': null,
  };
  // Clock correction is valid: revisions, rather than timestamps, order history.
  final archived = {
    ...first,
    'updated_at': '2026-11-05T11:00:00.000Z',
    'revision': 2,
    'archived_at': '2026-11-05T11:00:00.000Z',
  };
  await db.insert('audit_records', {'seq': 17, ...archived});
  await db.update(
    'sqlite_sequence',
    {'seq': 91},
    where: 'name = ?',
    whereArgs: ['audit_records'],
  );
  await db.insert('audit_events', {
    'id': eventId,
    'audit_id': auditId,
    'revision': 1,
    'action': 'CREATE',
    'actor_name': 'Original Auditor',
    'actor_profile_id': profileId,
    'created_at': first['updated_at'],
    'before_json': null,
    'after_json': jsonEncode(first),
  });
  await db.insert('audit_events', {
    'id': actorId,
    'audit_id': auditId,
    'revision': 2,
    'action': 'ARCHIVE',
    'actor_name': 'Renamed Auditor',
    'actor_profile_id': actorId,
    'created_at': archived['updated_at'],
    'before_json': jsonEncode(first),
    'after_json': jsonEncode(archived),
  });
  await db.execute('PRAGMA user_version = 1');
  return db;
}

void main() {
  setUpAll(sqfliteFfiInit);
  late Directory directory;
  late String path;
  setUp(() async {
    directory = await Directory.systemTemp.createTemp('bhli-migration-');
    path = '${directory.path}/v1.db';
  });
  tearDown(() async {
    await directory.delete(recursive: true);
  });

  test('fresh v2 starts empty and registers only the current local UUID on creation', () async {
    final repository = await SqliteOfflineRepository.open(
      path,
      factory: databaseFactoryFfi,
    );
    expect(await repository.profile(), isNull);
    final profile = await repository.saveProfile('Fictional Auditor');
    await repository.saveProfile('Renamed Auditor');
    await repository.close();
    final db = await databaseFactoryFfi.openDatabase(path);
    addTearDown(db.close);
    expect((await db.rawQuery('PRAGMA user_version')).single.values.single, 2);
    expect(await db.query('auditor_identities'), [
      {'id': profile.id},
    ]);
    expect(await db.query('audit_records'), isEmpty);
    expect(await db.query('audit_events'), isEmpty);
    expect(await db.query('transfer_receipts'), isEmpty);
    await db.close();
  });

  test(
    'populated v1 preserves sequence, raw snapshots and renamed profile at v2',
    () async {
      final old = await fixture(path);
      final records = await old.query('audit_records');
      final events = await old.query('audit_events', orderBy: 'revision');
      await old.execute('CREATE TABLE android_metadata (locale TEXT)');
      await old.insert('android_metadata', {'locale': 'en_US'});
      await old.close();
      final repository = await SqliteOfflineRepository.open(
        path,
        factory: databaseFactoryFfi,
      );
      expect((await repository.profile())!.name, 'Renamed Auditor');
      expect((await repository.read(auditId)).archived, isTrue);
      await repository.close();
      final db = await databaseFactoryFfi.openDatabase(path);
      try {
        expect(
          (await db.rawQuery('PRAGMA user_version')).single.values.single,
          2,
        );
        expect(await db.query('audit_records'), records);
        expect(
          (await db.query(
            'sqlite_sequence',
            where: 'name = ?',
            whereArgs: ['audit_records'],
          )).single['seq'],
          91,
        );
        expect(await db.query('audit_events', orderBy: 'revision'), events);
        expect(
          (await db.query('auditor_identities')).map((r) => r['id']).toSet(),
          {profileId, actorId},
        );
        expect(await db.query('transfer_receipts'), isEmpty);
        expect(
          (await db.rawQuery('PRAGMA foreign_key_list(audit_records)'))
              .single['table'],
          'auditor_identities',
        );
        expect(
          (await db.rawQuery('PRAGMA foreign_key_list(audit_events)'))
              .map((r) => r['table'])
              .toSet(),
          {'audit_records', 'auditor_identities'},
        );
        expect(await db.rawQuery('PRAGMA foreign_key_check'), isEmpty);
        expect((await db.query('android_metadata')).single['locale'], 'en_US');
      } finally {
        await db.close();
      }
      final restarted = await SqliteOfflineRepository.open(
        path,
        factory: databaseFactoryFfi,
      );
      await restarted.close();
    },
  );

  for (final mutation in [
    'constraint',
    'index',
    'trigger',
    'history',
    'identity',
    'foreign_key',
    'metadata',
    'values',
    'timestamp',
    'no_op_update',
  ]) {
    test(
      'rejects altered v1 $mutation without changing its schema or rows',
      () async {
        final db = await fixture(
          path,
          alteredTable: mutation == 'constraint'
              ? v1Tables[3].replaceFirst(
                  'CHECK(revision >= 1)',
                  'CHECK(revision >= 0)',
                )
              : null,
        );
        if (mutation == 'index') {
          await db.execute('DROP INDEX audit_records_station');
        }
        if (mutation == 'trigger') {
          await db.execute(
            'CREATE TRIGGER foreign_trigger AFTER INSERT ON app_meta BEGIN SELECT 1; END',
          );
        }
        if (mutation == 'history') {
          await db.delete('audit_events', where: 'revision = 1');
        }
        if (mutation == 'identity') {
          await db.update('audit_events', {'actor_profile_id': 'invalid'});
        }
        if (mutation == 'foreign_key') {
          await db.execute('PRAGMA foreign_keys = OFF');
          await db.update('audit_records', {'profile_id': actorId});
        }
        if (mutation == 'metadata') {
          await db.insert('app_meta', {
            'key': 'foreign_owner',
            'value': 'foreign',
          });
        }
        if (mutation == 'values') {
          await db.update('audit_records', {'plate_number': ' '});
        }
        if (mutation == 'timestamp') {
          for (final row in await db.query('audit_events')) {
            await db.update(
              'audit_events',
              {
                'created_at': (row['created_at'] as String).replaceAll(
                  '2026-11-05T',
                  '2026-02-30T',
                ),
                'before_json': (row['before_json'] as String?)?.replaceAll(
                  '2026-11-05T',
                  '2026-02-30T',
                ),
                'after_json': (row['after_json'] as String).replaceAll(
                  '2026-11-05T',
                  '2026-02-30T',
                ),
              },
              where: 'id = ?',
              whereArgs: [row['id']],
            );
          }
          await db.update('audit_records', {
            'created_at': '2026-02-30T12:00:00.000Z',
            'updated_at': '2026-02-30T11:00:00.000Z',
            'archived_at': '2026-02-30T11:00:00.000Z',
          });
        }
        if (mutation == 'no_op_update') {
          final last = (await db.query(
            'audit_events',
            where: 'revision = 2',
          )).single;
          final after =
              jsonDecode(last['after_json'] as String) as Map<String, dynamic>;
          after['archived_at'] = null;
          await db.update('audit_records', {'archived_at': null});
          await db.update('audit_events', {
            'action': 'UPDATE',
            'after_json': jsonEncode(after),
          }, where: 'revision = 2');
        }
        final schema = await db.rawQuery(
          'SELECT * FROM sqlite_master ORDER BY name',
        );
        final events = await db.query('audit_events');
        await db.close();
        await expectLater(
          SqliteOfflineRepository.open(path, factory: databaseFactoryFfi).then((
            repository,
          ) async {
            await repository.close();
            return repository;
          }),
          throwsA(
            isA<OfflineFailure>().having((e) => e.code, 'code', 'schema'),
          ),
        );
        final unchanged = await databaseFactoryFfi.openDatabase(path);
        expect(
          (await unchanged.rawQuery('PRAGMA user_version'))
              .single
              .values
              .single,
          1,
        );
        expect(
          await unchanged.rawQuery('SELECT * FROM sqlite_master ORDER BY name'),
          schema,
        );
        expect(await unchanged.query('audit_events'), events);
        await unchanged.close();
      },
    );
  }

  test(
    'real deferred COMMIT failure rolls back migration and permits restart',
    () async {
      final old = await fixture(path);
      final schema = await old.rawQuery(
        'SELECT * FROM sqlite_master ORDER BY name',
      );
      final records = await old.query('audit_records');
      final events = await old.query('audit_events');
      await old.close();
      await expectLater(
        SqliteOfflineRepository.open(path, factory: CommitFaultFactory()),
        throwsA(isA<OfflineFailure>().having((e) => e.code, 'code', 'storage')),
      );
      final db = await databaseFactoryFfi.openDatabase(path);
      expect(
        (await db.rawQuery('PRAGMA user_version')).single.values.single,
        1,
      );
      expect(
        await db.rawQuery('SELECT * FROM sqlite_master ORDER BY name'),
        schema,
      );
      expect(await db.query('audit_records'), records);
      expect(await db.query('audit_events'), events);
      await db.close();
      final restarted = await SqliteOfflineRepository.open(
        path,
        factory: databaseFactoryFfi,
      );
      await restarted.close();
    },
  );
}
