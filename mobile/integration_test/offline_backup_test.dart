// Fictional native core acceptance only. Never publish or bundle this test APK.
import 'dart:io';
import 'dart:convert';

import 'package:bhli_audit/offline/backup_evidence.dart';
import 'package:bhli_audit/offline/backup_state.dart';
import 'package:bhli_audit/offline/backup_store.dart';
import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/sqlite_repository.dart';
import 'package:bhli_audit/offline/store_lease.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:sqflite/sqflite.dart';

class _NoNetwork extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) =>
      throw StateError('Offline backup acceptance must not request HTTP.');
}

AuditValues _values(String station) => AuditValues(
  driverName: 'Fictional Native Auditor',
  helperName: 'Fictional Helper',
  auditDate: '2026-11-07',
  station: station,
  plateNumber: '00047',
  remarks: 'Fictional native backup acceptance only',
);
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  const run = String.fromEnvironment('DAMS_BACKUP_ACCEPTANCE_RUN');
  if (!validOfflineUuid(run)) {
    throw StateError(
      'A fresh guarded fictional backup acceptance run UUID is required.',
    );
  }
  setUp(() => HttpOverrides.global = _NoNetwork());
  tearDown(() => HttpOverrides.global = null);
  if (const bool.fromEnvironment('DAMS_BACKUP_PROCESS_PROBE')) {
    _registerProcessProbe(run);
    return;
  }
  testWidgets(
    'native SQLite and encrypted private durable recovery preserve every owned row after restore and reopen',
    (tester) async {
      await tester.runAsync(() async {
        final directory = Directory(
          '${await getDatabasesPath()}/acceptance-phase6e-$run',
        );
        if (await directory.exists()) {
          throw StateError(
            'Do not reuse or clear an earlier acceptance directory.',
          );
        }
        await directory.create();
        final path = '${directory.path}/fixture.db';
        final evidence = NativeBackupEvidence();
        var lease = await OfflineStoreLease.acquire();
        SqliteOfflineRepository? repository;
        try {
          expect(
            await evidence.readMarker(),
            isNull,
            reason: 'An existing recovery marker must be preserved and resolved before this fixture.',
          );
          repository = await SqliteOfflineRepository.open(
            path,
            factory: databaseFactory,
            ownership: lease,
          );
          await repository.saveProfile('Fictional Native Backup Auditor');
          final audit = await repository.create(
            newUuid(),
            _values('Fictional Candidate Station'),
          );
          await repository.archive(audit.id, audit.revision);
          final direct = await databaseFactory.openDatabase(
            path,
            options: OpenDatabaseOptions(
              singleInstance: false,
              onConfigure: (db) => db.execute('PRAGMA foreign_keys=ON'),
            ),
          );
          late List<Map<String, Object?>> metadata;
          try {
            await direct.transaction((txn) async {
              await txn.insert('auditor_identities', {'id': newUuid()});
              await txn.insert('transfer_receipts', {
                'package_id': newUuid(),
                'content_sha256': List.filled(64, 'a').join(),
                'source_installation_id': newUuid(),
                'imported_at': '2026-11-07T00:00:00.000000Z',
                'imported_count': 0,
              });
              await txn.rawUpdate(
                "UPDATE sqlite_sequence SET seq=90 WHERE name='audit_records'",
              );
              await txn.rawUpdate(
                "UPDATE audit_events SET after_json='  ' || after_json || '  '",
              );
            });
            metadata = await direct.query('android_metadata');
          } finally {
            await direct.close();
          }
          final candidate = await repository.captureBackup();
          final store = BackupStore(
            repository,
            evidence: evidence,
            scratchFactory: databaseFactory,
          );
          const password = 'fictional native backup passphrase only';
          final backup = await store.createBackup(password);
          expect(backup.state.digest, candidate.digest);
          await repository.saveProfile('Fictional Changed Current Profile');
          await repository.create(
            newUuid(),
            _values('Fictional Current Only Station'),
          );
          final preview = await store.inspectRestore(backup.bytes, password);
          expect(preview.unchanged, isFalse);
          var protected = false;
          final ticket = await store.prepareRestore(
            preview,
            password,
            publishRecovery: (artifact) async {
              // Core transport fixture: a second independently fsynced private file.
              // Successful system SAF interaction is a separate acceptance gate.
              final independent = await evidence.retain(artifact.bytes);
              final readback = await evidence.read(independent);
              protected = true;
              return readback;
            },
          );
          expect(protected, isTrue);
          final result = await store.applyRestore(ticket);
          expect(result.outcome, RestoreOutcome.restored);
          final restored = await repository.captureBackup();
          expect(restored.digest, candidate.digest);
          expect(restored.rows, candidate.rows);
          expect(restored.sequence, 90);
          final native = await databaseFactory.openDatabase(
            path,
            options: OpenDatabaseOptions(singleInstance: false),
          );
          try {
            expect(await native.query('android_metadata'), metadata);
          } finally {
            await native.close();
          }
          await repository.close();
          repository = null;
          lease = await OfflineStoreLease.acquire();
          repository = await SqliteOfflineRepository.open(
            path,
            factory: databaseFactory,
            ownership: lease,
          );
          expect((await repository.captureBackup()).digest, candidate.digest);
          expect(await evidence.readMarker(), isNull);
        } finally {
          await repository?.close();
          await lease.release();
          // Keep fictional DB and encrypted evidence for review; no broad cleanup.
        }
      });
    },
    timeout: const Timeout(Duration(minutes: 10)),
  );
}

// Nonshipping wrapper around the real queued owner. Every pause occurs in the
// actual replacement transaction or immediately after its checked native COMMIT.
class _PausingRepository implements OfflineBackupRepository {
  _PausingRepository(this.inner, this.barrier, this.phase, this.rows);
  final SqliteOfflineRepository inner;
  final File barrier;
  final String phase;
  final int rows;
  @override
  Future<BackupState> captureBackup() => inner.captureBackup();
  @override
  Future<T> withBackupMaintenance<T>(
    Future<T> Function(BackupMaintenance owner) work,
  ) => inner.withBackupMaintenance(
    (owner) => work(_PausingOwner(owner, barrier, phase, rows)),
  );
}

class _PausingOwner implements BackupMaintenance {
  _PausingOwner(this.inner, this.barrier, this.phase, this.rows);
  final BackupMaintenance inner;
  final File barrier;
  final String phase;
  final int rows;
  void _pause(int checks) {
    barrier.writeAsStringSync(
      jsonEncode({'phase': phase, 'checks': checks}),
      flush: true,
    );
    // Host must force-stop this fictional test process after seeing the barrier.
    // If it does not, fail visibly and let the real owner roll back normally.
    sleep(const Duration(seconds: 90));
    throw StateError(
      'The host did not terminate the guarded test process at its barrier.',
    );
  }

  @override
  Future<void> checkOwnership() => inner.checkOwnership();
  @override
  Future<BackupState> capture() => inner.capture();
  @override
  Future<BackupState> reopen() => inner.reopen();
  @override
  void blockWrites() => inner.blockWrites();
  @override
  void advanceGeneration() => inner.advanceGeneration();
  @override
  Future<void> replace(
    BackupState candidate,
    String expectedDigest, {
    bool Function()? cancel,
  }) async {
    var checks = 0;
    final target = phase == 'mid_delete'
        ? 4
        : phase == 'mid_insert'
        ? 8 + rows ~/ 2
        : phase == 'pre_commit'
        ? 9 + rows
        : -1;
    await inner.replace(
      candidate,
      expectedDigest,
      cancel: () {
        checks++;
        if (checks == target) _pause(checks);
        return cancel?.call() ?? false;
      },
    );
    if (phase == 'post_commit') _pause(checks);
  }
}

Map<String, Object?> _control(File file, String run) {
  final value = jsonDecode(file.readAsStringSync());
  const keys = {'version', 'run', 'mode', 'journal', 'pause'};
  if (value is! Map ||
      value.keys.toSet().difference(keys).isNotEmpty ||
      value.length != keys.length ||
      value['version'] != 1 ||
      value['run'] != run ||
      !['apply', 'reconcile'].contains(value['mode']) ||
      !['wal', 'delete'].contains(value['journal']) ||
      ![
        'mid_delete',
        'mid_insert',
        'pre_commit',
        'post_commit',
      ].contains(value['pause'])) {
    throw StateError('Invalid guarded fictional process-probe control.');
  }
  return Map<String, Object?>.from(value);
}

void _registerProcessProbe(String run) {
  testWidgets(
    'guarded real native restore process interruption and startup classification',
    (tester) async {
      await tester.runAsync(() async {
        final root = Directory(
          '${await getDatabasesPath()}/acceptance-phase6e-$run',
        );
        final control = _control(File('${root.path}/control.json'), run);
        final journal = control['journal'] as String,
            phase = control['pause'] as String;
        final directory = Directory('${root.path}/$journal-$phase');
        final path = '${directory.path}/fixture.db';
        final proof = File('${directory.path}/proof.json');
        final barrier = File('${directory.path}/barrier.json');
        final evidence = NativeBackupEvidence();
        final lease = await OfflineStoreLease.acquire();
        SqliteOfflineRepository? repository;
        try {
          if (control['mode'] == 'reconcile') {
            if (!await File(path).exists() || !await proof.exists()) {
              throw StateError(
                'Missing fictional interrupted fixture; never initialize a new store.',
              );
            }
            final expected = jsonDecode(await proof.readAsString()) as Map;
            expect(expected['run'], run);
            expect(expected['journal'], journal);
            expect(expected['pause'], phase);
            repository = await SqliteOfflineRepository.open(
              path,
              factory: databaseFactory,
              ownership: lease,
            );
            final outcome = await repository.withBackupMaintenance(
              (owner) => reconcileBackupStartup(owner, evidence),
            );
            final restored = phase == 'post_commit';
            expect(outcome, isNotNull);
            expect(
              outcome!.outcome,
              restored ? RestoreOutcome.restored : RestoreOutcome.original,
            );
            expect(
              (await repository.captureBackup()).digest,
              expected[restored ? 'intended_digest' : 'original_digest'],
            );
            expect(await evidence.readMarker(), isNull);
            await File('${directory.path}/reconciled.json').writeAsString(
              jsonEncode({
                'run': run,
                'journal': journal,
                'pause': phase,
                'outcome': outcome.outcome.name,
              }),
              flush: true,
            );
            return;
          }
          if (await directory.exists()) {
            throw StateError(
              'Never reuse, overwrite or clear an interrupted fictional case.',
            );
          }
          await directory.create(recursive: true);
          expect(
            await evidence.readMarker(),
            isNull,
            reason:
                'Reconcile the preceding fixture before starting a new one.',
          );
          repository = await SqliteOfflineRepository.open(
            path,
            factory: databaseFactory,
            ownership: lease,
          );
          await repository.saveProfile('Fictional Process Candidate');
          final audit = await repository.create(
            newUuid(),
            _values('Fictional Candidate'),
          );
          await repository.archive(audit.id, audit.revision);
          final candidate = await repository.captureBackup();
          final real = BackupStore(
            repository,
            evidence: evidence,
            scratchFactory: databaseFactory,
          );
          const password = 'fictional process interruption passphrase';
          final backup = await real.createBackup(password);
          await repository.saveProfile('Fictional Protected Original');
          await repository.create(
            newUuid(),
            _values('Fictional Original Only'),
          );
          final original = await repository.captureBackup();
          final native = await databaseFactory.openDatabase(
            path,
            options: OpenDatabaseOptions(singleInstance: false),
          );
          try {
            expect(
              (await native.rawQuery('PRAGMA journal_mode=$journal'))
                  .single
                  .values
                  .single,
              journal,
            );
          } finally {
            await native.close();
          }
          final rows = candidate.rows.values.fold<int>(
            0,
            (total, rows) => total + rows.length,
          );
          final wrapped = BackupStore(
            _PausingRepository(repository, barrier, phase, rows),
            evidence: evidence,
            scratchFactory: databaseFactory,
          );
          final preview = await wrapped.inspectRestore(backup.bytes, password);
          final ticket = await wrapped.prepareRestore(
            preview,
            password,
            publishRecovery: (artifact) async {
              final separate = await evidence.retain(artifact.bytes);
              return evidence.read(separate);
            },
          );
          await proof.writeAsString(
            jsonEncode({
              'version': 1,
              'run': run,
              'journal': journal,
              'pause': phase,
              'original_digest': original.digest,
              'intended_digest': candidate.digest,
              'candidate_rows': rows,
            }),
            flush: true,
          );
          final result = await wrapped.applyRestore(ticket);
          throw StateError(
            'Host interruption was not executed; observed ${result.outcome.name}. This is not a passing crash drill.',
          );
        } finally {
          await repository?.close();
          await lease.release();
        }
      });
    },
    timeout: const Timeout(Duration(minutes: 5)),
  );
}
