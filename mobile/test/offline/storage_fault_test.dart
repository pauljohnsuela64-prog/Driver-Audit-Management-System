import 'dart:io';

import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/sqlite_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

class FaultFactory extends DatabaseFactory {
  late Database connection;
  @override
  Future<Database> openDatabase(String path, {OpenDatabaseOptions? options}) async =>
      connection = await databaseFactoryFfi.openDatabase(path, options: options);
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  setUpAll(sqfliteFfiInit);
  late Directory directory;
  late FaultFactory factory;
  late SqliteOfflineRepository repository;
  setUp(() async {
    directory = await Directory.systemTemp.createTemp('bhli-offline-fault-');
    factory = FaultFactory();
    repository = await SqliteOfflineRepository.open(
      '${directory.path}/test.db', factory: factory,
    );
    await repository.saveProfile('Fictional fault tester');
  });
  tearDown(() async {
    await repository.close();
    await directory.delete(recursive: true);
  });
  AuditValues values({String? remarks}) => AuditValues(
    driverName: 'Fictional Driver', auditDate: '2026-11-05',
    station: 'Fictional Station', plateNumber: '00047', remarks: remarks,
  );
  final storageFailure = isA<OfflineFailure>()
      .having((error) => error.code, 'safe code', 'storage');

  test('SQLite full error rolls back record and history without exposing SQL', () async {
    final db = factory.connection;
    final count = (await db.rawQuery('PRAGMA page_count')).single.values.single as int;
    await db.execute('PRAGMA max_page_count = $count');
    final id = newUuid();
    await expectLater(repository.create(id, values(remarks: 'X' * 10000)), throwsA(storageFailure));
    expect((await repository.list(const AuditFilter())).total, 0);
    expect(await db.query('audit_events'), isEmpty);
    expect((await repository.profile())!.name, 'Fictional fault tester');
  });

  test('deferred constraint failure at COMMIT rolls back both audit and event', () async {
    final db = factory.connection;
    // Real deferred FK failure: INSERT succeeds and COMMIT is rejected.
    await db.execute('CREATE TABLE fault_parent(id INTEGER PRIMARY KEY)');
    await db.execute('CREATE TABLE fault_deferred(parent_id INTEGER REFERENCES fault_parent(id) DEFERRABLE INITIALLY DEFERRED)');
    await db.execute('CREATE TRIGGER fault_commit AFTER INSERT ON audit_events BEGIN INSERT INTO fault_deferred VALUES(999); END');
    await expectLater(repository.create(newUuid(), values()), throwsA(storageFailure));
    expect((await repository.list(const AuditFilter())).total, 0);
    expect(await db.query('audit_events'), isEmpty);
    expect(await db.query('fault_deferred'), isEmpty);
    expect(await db.rawQuery('PRAGMA foreign_key_check'), isEmpty);
    await db.execute('DROP TRIGGER fault_commit');
    expect((await repository.create(newUuid(), values())).revision, 1);
  });
}
