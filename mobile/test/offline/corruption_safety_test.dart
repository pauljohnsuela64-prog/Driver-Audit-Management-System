import 'dart:io';

import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/sqlite_repository.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

class CorruptionFactory implements DatabaseFactory {
  bool failNext = false;
  int transactions = 0;
  @override
  Future<Database> openDatabase(
    String path, {
    OpenDatabaseOptions? options,
  }) async => CorruptionDatabase(
    await databaseFactoryFfi.openDatabase(path, options: options),
    this,
  );
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class CorruptionDatabase implements Database {
  CorruptionDatabase(this.inner, this.owner);
  final Database inner;
  final CorruptionFactory owner;
  @override
  Future<T> transaction<T>(
    Future<T> Function(Transaction txn) action, {
    bool? exclusive,
  }) async {
    owner.transactions++;
    if (owner.failNext) {
      owner.failNext = false;
      throw PlatformException(
        code: 'sqlite_error',
        message: 'BHLI_OFFLINE_CORRUPTION',
      );
    }
    return inner.transaction(action, exclusive: exclusive);
  }

  @override
  Future<void> close() => inner.close();
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class WritableRecoveryFactory implements DatabaseFactory {
  @override
  Future<Database> openDatabase(
    String path, {
    OpenDatabaseOptions? options,
  }) async {
    if (options?.readOnly == true) {
      // Actual API36 refusal observed with a journal requiring normal recovery.
      throw PlatformException(
        code: 'sqlite_error',
        message: 'attempt to write a readonly database (code 776 SQLITE_READONLY_ROLLBACK)',
      );
    }
    return databaseFactoryFfi.openDatabase(path, options: options);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  setUpAll(sqfliteFfiInit);
  late Directory directory;
  setUp(
    () async =>
        directory = await Directory.systemTemp.createTemp('bhli-corruption-'),
  );
  tearDown(() async => directory.delete(recursive: true));
  final recovery = isA<OfflineFailure>().having(
    (error) => error.code,
    'code',
    'recovery_required',
  );

  test(
    'normal existing-store recovery is not prevented by a read-only preflight',
    () async {
      final path = '${directory.path}/normal-recovery.db';
      final original = await SqliteOfflineRepository.open(
        path,
        factory: databaseFactoryFfi,
      );
      await original.saveProfile('Fictional journal recovery tester');
      final record = await original.create(
        newUuid(),
        AuditValues(
          driverName: 'Fictional Driver',
          auditDate: '2026-11-07',
          station: 'Fictional Station',
          plateNumber: '00047',
        ),
      );
      await original.close();
      final reopened = await SqliteOfflineRepository.open(
        path,
        factory: WritableRecoveryFactory(),
      );
      try {
        expect(
          (await reopened.read(record.id)).auditedByName,
          'Fictional journal recovery tester',
        );
        expect((await reopened.list(const AuditFilter())).total, 1);
      } finally {
        await reopened.close();
      }
    },
  );

  test(
    'persisted corruption flag prevents fresh initialization on restart',
    () async {
      final path = '${directory.path}/flagged.db';
      await File('$path.bhli-corrupt')
          .writeAsString('Corruption detected', flush: true);
      await expectLater(
        SqliteOfflineRepository.open(path, factory: databaseFactoryFfi),
        throwsA(recovery),
      );
      expect(await File(path).exists(), isFalse);
    },
  );

  test('real corrupt header is refused without replacing its bytes', () async {
    final file = File('${directory.path}/corrupt-header.db');
    final original = List.filled(4096, 65);
    await file.writeAsBytes(original, flush: true);
    await expectLater(
      SqliteOfflineRepository.open(file.path, factory: databaseFactoryFfi),
      throwsA(recovery),
    );
    expect(await file.readAsBytes(), original);
    expect(await File('${file.path}.bhli-corrupt').exists(), isTrue);
  });

  test(
    'existing zero-byte store is preserved rather than initialized',
    () async {
      final file = await File('${directory.path}/damaged.db').create();
      await expectLater(
        SqliteOfflineRepository.open(file.path, factory: databaseFactoryFfi),
        throwsA(recovery),
      );
      expect(await file.length(), 0);
    },
  );

  test(
    'existing empty SQLite store is not mistaken for an absent fresh install',
    () async {
      final path = '${directory.path}/empty.db';
      final db = await databaseFactoryFfi.openDatabase(path);
      await db.execute('PRAGMA user_version = 0');
      await db.close();
      final before = await File(path).readAsBytes();
      await expectLater(
        SqliteOfflineRepository.open(path, factory: databaseFactoryFfi),
        throwsA(recovery),
      );
      expect(await File(path).readAsBytes(), before);
    },
  );

  test(
    'native corruption blocks already queued and later operations',
    () async {
      final factory = CorruptionFactory();
      final repo = await SqliteOfflineRepository.open(
        '${directory.path}/fresh.db',
        factory: factory,
      );
      try {
        await repo.saveProfile('Fictional corruption tester');
        final before = factory.transactions;
        factory.failNext = true;
        final first = repo.profile();
        final queued = repo.saveProfile('Must not write');
        await Future.wait([
          expectLater(first, throwsA(recovery)),
          expectLater(queued, throwsA(recovery)),
        ]);
        await expectLater(repo.profile(), throwsA(recovery));
        expect(factory.transactions, before + 1);
        expect(
          await File('${directory.path}/fresh.db.bhli-corrupt').exists(),
          isTrue,
        );
      } finally {
        await repo.close();
      }
    },
  );
}
