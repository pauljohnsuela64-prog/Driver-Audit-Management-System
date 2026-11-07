import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/sqlite_repository.dart';

AuditValues values([String driver = 'Driver']) => AuditValues(
  driverName: driver,
  auditDate: '2026-11-05',
  station: 'North',
  plateNumber: 'ABC',
);
Matcher failure(String code) =>
    isA<OfflineFailure>().having((e) => e.code, 'code', code);

// Capture the real connection through the supported factory seam; no fake SQL.
class CapturingFactory extends DatabaseFactory {
  late Database connection;
  @override
  Future<Database> openDatabase(
    String path, {
    OpenDatabaseOptions? options,
  }) async => connection = await databaseFactoryFfi.openDatabase(
    path,
    options: options,
  );
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

// Android creates its locale table inside native open, after the repository's
// fresh-file check but before Dart onConfigure. Model that ordering faithfully.
class AndroidMetadataFactory extends CapturingFactory {
  @override
  Future<Database> openDatabase(
    String path, {
    OpenDatabaseOptions? options,
  }) async {
    if (!await File(path).exists()) {
      final platform = await databaseFactoryFfi.openDatabase(path);
      await platform.execute('CREATE TABLE android_metadata (locale TEXT)');
      await platform.insert('android_metadata', {'locale': 'en_US'});
      await platform.close();
    }
    return super.openDatabase(path, options: options);
  }
}

void main() {
  late Directory directory;
  late String path;
  late SqliteOfflineRepository repo;
  setUpAll(sqfliteFfiInit);
  setUp(() async {
    directory = await Directory.systemTemp.createTemp('bhli-offline-test-');
    path = '${directory.path}/test.db';
    repo = await SqliteOfflineRepository.open(
      path,
      factory: databaseFactoryFfi,
    );
  });
  tearDown(() async {
    await repo.close();
    await directory.delete(recursive: true);
  });

  test(
    'Android platform metadata permits fresh initialization and reopen',
    () async {
      final nativePath = '${directory.path}/android-platform.db';
      var native = await SqliteOfflineRepository.open(
        nativePath,
        factory: AndroidMetadataFactory(),
      );
      try {
        expect(await native.profile(), isNull);
        expect((await native.list(const AuditFilter())).total, 0);
        await native.saveProfile('Fictional Platform Auditor');
        final record = await native.create(newUuid(), values());
        await native.close();
        native = await SqliteOfflineRepository.open(
          nativePath,
          factory: databaseFactoryFfi,
        );
        expect(
          (await native.read(record.id)).auditedByName,
          'Fictional Platform Auditor',
        );
      } finally {
        await native.close();
      }
      final inspection = await databaseFactoryFfi.openDatabase(nativePath);
      expect(
        (await inspection.query('android_metadata')).single['locale'],
        'en_US',
      );
      await inspection.close();
    },
  );
  test('empty installation requires profile and preserves historic actor on rename', () async {
    expect(await repo.profile(), isNull);
    expect((await repo.list(AuditFilter())).total, 0);
    await expectLater(
      repo.create(newUuid(), values()),
      throwsA(failure('profile_required')),
    );
    final profile = await repo.saveProfile(' Alice ');
    final first = await repo.create(newUuid(), values());
    await repo.saveProfile('Bob');
    final second = await repo.create(newUuid(), values());
    expect(profile.name, 'Alice');
    expect(first.auditedByName, 'Alice');
    expect(second.auditedByName, 'Bob');
    expect(second.profileId, profile.id);
    await repo.close();
    repo = await SqliteOfflineRepository.open(
      path,
      factory: databaseFactoryFfi,
    );
    expect((await repo.read(first.id)).auditedByName, 'Alice');
    expect((await repo.profile())!.name, 'Bob');
  });
  test(
    'create retries compare original content after edit and preserve history',
    () async {
      await repo.saveProfile('Alice');
      final id = newUuid();
      await repo.create(id, values());
      final edited = await repo.update(id, 1, values('Edited'));
      expect((await repo.create(id, values())).revision, 2);
      await expectLater(
        repo.create(id, values('Other')),
        throwsA(failure('conflict')),
      );
      await expectLater(
        repo.update(id, 1, values()),
        throwsA(failure('conflict')),
      );
      await expectLater(repo.archive(id, 1), throwsA(failure('conflict')));
      expect((await repo.update(id, 2, values('Edited'))).revision, 2);
      final events = await repo.history(id);
      expect(events.length, 2);
      expect(events.last.action, 'CREATE');
      expect(events.last.after!['audited_by_name'], 'Alice');
      expect(edited.values.driverName, 'Edited');
      final archived = await repo.archive(id, 2);
      expect(archived.archived, isTrue);
      await expectLater(
        repo.create(id, values()),
        throwsA(failure('conflict')),
      );
      await expectLater(
        repo.update(id, 3, values()),
        throwsA(failure('conflict')),
      );
      expect((await repo.list(AuditFilter())).total, 0);
      expect((await repo.list(AuditFilter(includeArchived: true))).total, 1);
    },
  );
  test('validates profiles filters and identifiers before storing', () async {
    await expectLater(repo.saveProfile(' '), throwsA(failure('validation')));
    await repo.saveProfile('Alice');
    await expectLater(
      repo.create('bad', values()),
      throwsA(failure('validation')),
    );
    for (final filter in [
      AuditFilter(page: 0),
      AuditFilter(pageSize: 0),
      AuditFilter(sort: 'DROP TABLE'),
      AuditFilter(dateFrom: '2026-02-30'),
      AuditFilter(dateFrom: '2026-11-06', dateTo: '2026-11-05'),
    ]) {
      await expectLater(repo.list(filter), throwsA(failure('validation')));
    }
    await expectLater(repo.read(newUuid()), throwsA(failure('not_found')));
  });
  test(
    'literal filters and stable pagination return expected records',
    () async {
      await repo.saveProfile('Alice');
      await repo.create(newUuid(), values('100% Driver'));
      await repo.create(newUuid(), values('Other'));
      expect((await repo.list(AuditFilter(driver: '%'))).total, 1);
      final page = await repo.list(
        AuditFilter(sort: 'created', pageSize: 1, page: 2),
      );
      expect(page.total, 2);
      expect(page.pageSize, 1);
      expect(page.items.single.values.driverName, 'Other');
    },
  );
  test(
    'history insert failure rolls back record and revision atomically',
    () async {
      await repo.saveProfile('Alice');
      final id = newUuid();
      await repo.create(id, values());
      final db = await databaseFactoryFfi.openDatabase(path);
      await db.execute(
        "CREATE TRIGGER reject_event BEFORE INSERT ON audit_events BEGIN SELECT RAISE(ABORT, 'private SQL path'); END",
      );
      await expectLater(
        repo.update(id, 1, values('Changed')),
        throwsA(failure('storage')),
      );
      expect((await repo.read(id)).revision, 1);
      expect((await repo.history(id)).length, 1);
      await db.execute('DROP TRIGGER reject_event');
      await db.close();
    },
  );
  test('close drains admitted writes and rejects later operations', () async {
    final saving = repo.saveProfile('Alice');
    final closing = repo.close();
    expect((await saving).name, 'Alice');
    await closing;
    await expectLater(repo.profile(), throwsA(failure('closed')));
  });
  test('newer schemas are rejected without modifying their records', () async {
    await repo.close();
    final db = await databaseFactoryFfi.openDatabase(path);
    await db.execute('PRAGMA user_version = 3');
    await db.close();
    await expectLater(
      SqliteOfflineRepository.open(path, factory: databaseFactoryFfi),
      throwsA(failure('schema')),
    );
    final check = await databaseFactoryFfi.openDatabase(path);
    expect(await check.getVersion(), 3);
    expect(await check.query('app_meta'), isNotEmpty);
    await check.execute('PRAGMA user_version = 2');
    await check.close();
  });
  test('foreign keys are enabled on the repository connection', () async {
    await repo.close();
    final factory = CapturingFactory();
    repo = await SqliteOfflineRepository.open(path, factory: factory);
    expect(
      (await factory.connection.rawQuery('PRAGMA foreign_keys'))
          .single
          .values
          .single,
      1,
    );
    await expectLater(
      factory.connection.rawInsert(
        "INSERT INTO audit_events(id,audit_id,revision,action,actor_name,actor_profile_id,created_at,after_json) VALUES(?,?,1,'CREATE','A','profile','2026-11-05T00:00:00Z','{}')",
        [newUuid(), newUuid()],
      ),
      throwsA(isA<DatabaseException>()),
    );
  });
  test(
    'read-only and externally closed storage errors are sanitized',
    () async {
      await repo.close();
      final factory = CapturingFactory();
      repo = await SqliteOfflineRepository.open(path, factory: factory);
      await factory.connection.execute('PRAGMA query_only = ON');
      await expectLater(
        repo.saveProfile('Alice'),
        throwsA(
          isA<OfflineFailure>()
              .having((e) => e.code, 'code', 'storage')
              .having(
                (e) => e.message,
                'safe message',
                isNot(contains(directory.path)),
              ),
        ),
      );
      await factory.connection.execute('PRAGMA query_only = OFF');
      expect(await repo.profile(), isNull);
      await factory.connection.close();
      await expectLater(repo.profile(), throwsA(failure('storage')));
    },
  );
  test('history failure also rolls back create and archive', () async {
    await repo.saveProfile('Alice');
    final original = await repo.create(newUuid(), values());
    final db = await databaseFactoryFfi.openDatabase(path);
    try {
      await db.execute(
        "CREATE TRIGGER reject_event BEFORE INSERT ON audit_events BEGIN SELECT RAISE(ABORT, 'private path'); END",
      );
      final id = newUuid();
      await expectLater(repo.create(id, values()), throwsA(failure('storage')));
      await expectLater(repo.read(id), throwsA(failure('not_found')));
      await expectLater(
        repo.archive(original.id, 1),
        throwsA(failure('storage')),
      );
      expect((await repo.read(original.id)).archived, false);
      expect((await repo.history(original.id)).length, 1);
    } finally {
      await db.close();
    }
  });
  test('profile rename and create serialize in admission order', () async {
    await repo.saveProfile('Before');
    final creation = repo.create(newUuid(), values());
    final rename = repo.saveProfile('After');
    final later = repo.create(newUuid(), values());
    expect((await creation).auditedByName, 'Before');
    await rename;
    expect((await later).auditedByName, 'After');
  });
  test('incomplete version one schema is refused as schema failure', () async {
    await repo.close();
    final db = await databaseFactoryFfi.openDatabase(path);
    await db.execute(
      'ALTER TABLE audit_events RENAME COLUMN actor_name TO unknown_name',
    );
    await db.close();
    await expectLater(
      SqliteOfflineRepository.open(path, factory: databaseFactoryFfi),
      throwsA(failure('schema')),
    );
  });
  test('uppercase UUIDs cannot create a second semantic identity', () async {
    await repo.saveProfile('Alice');
    final id = newUuid();
    await repo.create(id, values());
    await expectLater(
      repo.create(id.toUpperCase(), values()),
      throwsA(failure('validation')),
    );
    expect((await repo.list(AuditFilter())).total, 1);
  });
  test('event actor includes stable local profile identity', () async {
    final profile = await repo.saveProfile('Alice');
    final record = await repo.create(newUuid(), values());
    expect((await repo.history(record.id)).single.actorProfileId, profile.id);
  });
}
