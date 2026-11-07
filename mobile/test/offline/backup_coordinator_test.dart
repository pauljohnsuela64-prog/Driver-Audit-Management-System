import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:bhli_audit/offline/backup_crypto.dart';
import 'package:bhli_audit/offline/backup_state.dart';
import 'package:bhli_audit/offline/backup_store.dart';
import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/sqlite_repository.dart';
import 'package:bhli_audit/offline/store_lease.dart';

class Ownership implements StoreOwnership {
  bool released = false;
  int checked = 0;
  @override
  Future<void> ensureHeld() async {
    checked++;
    if (released) throw StateError('released');
  }

  @override
  Future<void> release() async {
    released = true;
  }
}

class Evidence implements BackupEvidence {
  final files = <String, Uint8List>{};
  Uint8List? marker;
  bool markerFailure = false;
  bool clearFailure = false;
  bool disappearMarker = false;
  int markerReads = 0;
  @override
  Future<String> retain(Uint8List envelope) async {
    final name = '${newUuid()}.bhlibackup';
    files[name] = Uint8List.fromList(envelope);
    return name;
  }

  @override
  Future<Uint8List> read(String handle) async =>
      Uint8List.fromList(files[handle]!);
  @override
  Future<Uint8List?> readMarker() async {
    if (marker != null && disappearMarker && ++markerReads > 1) marker = null;
    return marker == null ? null : Uint8List.fromList(marker!);
  }

  @override
  Future<void> writeMarker(Uint8List bytes) async {
    if (markerFailure || marker != null) throw StateError('marker unavailable');
    marker = Uint8List.fromList(bytes);
  }

  @override
  Future<void> clearMarker() async {
    if (clearFailure) throw StateError('injected cleanup');
    marker = null;
  }
}

class FaultFactory implements DatabaseFactory {
  int calls = 0;
  bool loseCommitAck = false;
  bool failReopen = false;
  @override
  Future<Database> openDatabase(
    String path, {
    OpenDatabaseOptions? options,
  }) async {
    calls++;
    if (failReopen && calls > 1) throw StateError('injected reopen failure');
    return FaultDatabase(
      await databaseFactoryFfi.openDatabase(path, options: options),
      this,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class FaultDatabase implements Database {
  FaultDatabase(this.inner, this.factory);
  final Database inner;
  final FaultFactory factory;
  @override
  Future<T> transaction<T>(
    Future<T> Function(Transaction txn) action, {
    bool? exclusive,
  }) async {
    final result = await inner.transaction(action, exclusive: exclusive);
    if (exclusive == true && factory.loseCommitAck) {
      factory.loseCommitAck = false;
      throw StateError('actual COMMIT completed, acknowledgement lost');
    }
    return result;
  }

  @override
  Future<void> execute(String sql, [List<Object?>? arguments]) =>
      inner.execute(sql, arguments);
  @override
  Future<List<Map<String, Object?>>> rawQuery(
    String sql, [
    List<Object?>? arguments,
  ]) => inner.rawQuery(sql, arguments);
  @override
  Future<void> close() => inner.close();
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

const password = 'fictional backup password only';
void main() {
  setUpAll(sqfliteFfiInit);
  late Directory dir;
  late SqliteOfflineRepository repo;
  late Ownership lease;
  late Evidence evidence;
  late BackupStore store;
  late Uint8List encrypted;
  late FaultFactory factory;
  setUp(() async {
    dir = Directory.systemTemp.createTempSync('bhli-restore-core-');
    lease = Ownership();
    evidence = Evidence();
    factory = FaultFactory();
    repo = await SqliteOfflineRepository.open(
      '${dir.path}/owned.db',
      factory: factory,
      ownership: lease,
    );
    store = BackupStore(
      repo,
      evidence: evidence,
      scratchFactory: databaseFactoryFfi,
    );
    encrypted = await sealBackup(
      File('test/fixtures/backup/python-android-state.ndjson')
          .readAsBytesSync(),
      password,
      platform: 'android',
    );
  });
  tearDown(() async {
    await repo.close();
    dir.deleteSync(recursive: true);
  });
  test('recovery publication and authentication precede opaque confirmation ticket', () async {
    final preview = await store.inspectRestore(encrypted, password);
    final original = await repo.captureBackup();
    var published = false;
    final ticket = await store.prepareRestore(
      preview,
      password,
      publishRecovery: (artifact) async {
        final state = decodeBackupState(
          await openBackup(artifact.bytes, password, platform: 'android'),
          platform: 'android',
        );
        expect(state.digest, original.digest);
        published = true;
        return artifact.bytes;
      },
    );
    expect(published, isTrue);
    expect(evidence.files.length, 2);
    await expectLater(
      repo.saveProfile('Blocked'),
      throwsA(isA<OfflineFailure>()),
    );
    final result = await store.applyRestore(ticket);
    expect(result.outcome, RestoreOutcome.restored);
    expect((await repo.captureBackup()).digest, preview.candidate.digest);
    expect(evidence.marker, isNull);
    expect(evidence.files.length, 2);
    expect(lease.checked, greaterThan(0));
    await expectLater(
      store.applyRestore(ticket),
      throwsA(isA<BackupStoreFailure>()),
    );
  });
  test(
    'unverified mandatory recovery never yields a ticket or changes owned rows',
    () async {
      final preview = await store.inspectRestore(encrypted, password);
      final before = await repo.captureBackup();
      await expectLater(
        store.prepareRestore(
          preview,
          password,
          publishRecovery: (artifact) async => Uint8List(0),
        ),
        throwsA(anything),
      );
      expect((await repo.captureBackup()).digest, before.digest);
      await repo.saveProfile('Available');
      expect(evidence.marker, isNull);
    },
  );
  test('cancel after recovery retains encrypted evidence and leaves original state', () async {
    final preview = await store.inspectRestore(encrypted, password);
    final before = await repo.captureBackup();
    final ticket = await store.prepareRestore(
      preview,
      password,
      publishRecovery: (artifact) async => artifact.bytes,
    );
    await store.cancelPrepared(ticket);
    expect((await repo.captureBackup()).digest, before.digest);
    expect(evidence.files.length, 2);
    expect(evidence.marker, isNull);
    await repo.saveProfile('Available');
  });
  test('actual COMMIT then lost acknowledgement is classified RESTORED after reopen', () async {
    final preview = await store.inspectRestore(encrypted, password);
    final ticket = await store.prepareRestore(
      preview,
      password,
      publishRecovery: (artifact) async => artifact.bytes,
    );
    factory.loseCommitAck = true;
    final result = await store.applyRestore(ticket);
    expect(result.outcome, RestoreOutcome.restored);
    expect(factory.loseCommitAck, isFalse);
    expect(factory.calls, 2);
    expect((await repo.captureBackup()).digest, preview.candidate.digest);
    expect(repo.storeGeneration, 1);
  });
  test('unreadable reopened outcome is UNKNOWN and blocks all subsequent mutations', () async {
    final preview = await store.inspectRestore(encrypted, password);
    final ticket = await store.prepareRestore(
      preview,
      password,
      publishRecovery: (artifact) async => artifact.bytes,
    );
    factory.failReopen = true;
    final result = await store.applyRestore(ticket);
    expect(result.outcome, RestoreOutcome.unknown);
    expect(evidence.marker, isNotNull);
    expect(evidence.files.length, 2);
    await expectLater(
      repo.saveProfile('Forbidden'),
      throwsA(isA<OfflineFailure>()),
    );
    final independent = await databaseFactoryFfi.openDatabase(
      '${dir.path}/owned.db',
      options: OpenDatabaseOptions(
        singleInstance: false,
        onConfigure: (db) => db.execute('PRAGMA foreign_keys=ON'),
      ),
    );
    try {
      expect(
        (await independent.transaction(captureBackupTransaction)).digest,
        preview.candidate.digest,
      );
    } finally {
      await independent.close();
    }
  });
  test(
    'corrupt startup marker cannot authorize replay and blocks writes',
    () async {
      evidence.marker = Uint8List.fromList([123, 125, 10]);
      final result = await repo.withBackupMaintenance(
        (owner) => reconcileBackupStartup(owner, evidence),
      );
      expect(result!.outcome, RestoreOutcome.unknown);
      await expectLater(
        repo.saveProfile('Forbidden'),
        throwsA(isA<OfflineFailure>()),
      );
      expect(evidence.marker, isNotNull);
    },
  );
  test('cancellation after final confirmation and before transaction rolls back truthfully', () async {
    final preview = await store.inspectRestore(encrypted, password);
    final before = await repo.captureBackup();
    final ticket = await store.prepareRestore(
      preview,
      password,
      publishRecovery: (artifact) async => artifact.bytes,
    );
    final applying = store.applyRestore(ticket);
    store.requestCancel(ticket);
    expect((await applying).outcome, RestoreOutcome.original);
    expect((await repo.captureBackup()).digest, before.digest);
  });
  test('failed owner admission rejects preparation rather than stranding its ticket future', () async {
    final preview = await store.inspectRestore(encrypted, password);
    lease.released = true;
    await expectLater(
      store
          .prepareRestore(
            preview,
            password,
            publishRecovery: (artifact) async => artifact.bytes,
          )
          .timeout(const Duration(seconds: 2)),
      throwsA(isA<StateError>()),
    );
    expect(evidence.marker, isNull);
  });
  test('missing required marker after checked replacement is UNKNOWN and blocks writes', () async {
    final preview = await store.inspectRestore(encrypted, password);
    final ticket = await store.prepareRestore(
      preview,
      password,
      publishRecovery: (artifact) async => artifact.bytes,
    );
    evidence.disappearMarker = true;
    final result = await store.applyRestore(ticket);
    expect(result.outcome, RestoreOutcome.unknown);
    await expectLater(
      repo.saveProfile('Forbidden'),
      throwsA(isA<OfflineFailure>()),
    );
  });
  test(
    'known restored outcome with marker cleanup failure remains write blocked',
    () async {
      final preview = await store.inspectRestore(encrypted, password);
      final ticket = await store.prepareRestore(
        preview,
        password,
        publishRecovery: (artifact) async => artifact.bytes,
      );
      evidence.clearFailure = true;
      final result = await store.applyRestore(ticket);
      expect(result.outcome, RestoreOutcome.restored);
      expect(result.warning, isNotEmpty);
      expect(evidence.marker, isNotNull);
      await expectLater(
        repo.saveProfile('Forbidden'),
        throwsA(isA<OfflineFailure>()),
      );
    },
  );
  test('required marker write failure aborts before replacement', () async {
    final preview = await store.inspectRestore(encrypted, password);
    final before = await repo.captureBackup();
    final ticket = await store.prepareRestore(
      preview,
      password,
      publishRecovery: (artifact) async => artifact.bytes,
    );
    evidence.markerFailure = true;
    await expectLater(store.applyRestore(ticket), throwsA(anything));
    expect((await repo.captureBackup()).digest, before.digest);
  });
}
