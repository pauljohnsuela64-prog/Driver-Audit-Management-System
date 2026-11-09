import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/sqlite_repository.dart';
import 'package:bhli_audit/offline/backup_store.dart';
import 'package:bhli_audit/offline/store_lease.dart';
import 'package:bhli_audit/offline/backup_state.dart';
import 'package:bhli_audit/offline/backup_crypto.dart';

// Host-only evidence adapter, real files/readback. Not Android SAF/fsync acceptance.
class FilesEvidence implements BackupEvidence {
  FilesEvidence(this.root) {
    root.createSync(recursive: true);
  }
  final Directory root;
  bool failRetain = false;
  File file(String name) {
    if (name.contains('/') || name.contains('\\')) throw StateError('unsafe');
    return File('${root.path}/$name');
  }

  @override
  Future<String> retain(Uint8List bytes) async {
    if (failRetain) {
      throw const FileSystemException('Injected unavailable backup storage');
    }
    final name = '${newUuid()}.bhlibackup';
    await file(name).writeAsBytes(bytes, flush: true);
    return name;
  }

  @override
  Future<Uint8List> read(String name) => file(name).readAsBytes();
  @override
  Future<Uint8List?> readMarker() async =>
      await file('marker').exists() ? await file('marker').readAsBytes() : null;
  @override
  Future<void> writeMarker(Uint8List bytes) async {
    if (await file('marker').exists()) throw StateError('exists');
    await file('marker').writeAsBytes(bytes, flush: true);
  }

  @override
  Future<void> clearMarker() async {
    if (await file('marker').exists()) await file('marker').delete();
  }
}

class HostOwnership implements StoreOwnership {
  HostOwnership(String path)
    : file = File(path).openSync(mode: FileMode.append) {
    file.lockSync(FileLock.exclusive);
  }
  final RandomAccessFile file;
  bool released = false;
  @override
  Future<void> ensureHeld() async {
    if (released) throw StateError('released');
  }

  @override
  Future<void> release() async {
    if (!released) {
      file.unlockSync();
      file.closeSync();
      released = true;
    }
  }
}

AuditValues values(String name) => AuditValues(
  driverName: name,
  helperName: 'Fictional Helper',
  auditDate: '2026-11-09',
  station: 'Fictional Station',
  plateNumber: '000123',
  remarks: 'Fictional Unicode \u65e5\u672c\u8a9e \u{1f69a}',
);
void main() {
  setUpAll(sqfliteFfiInit);
  test('oversize plaintext and envelope are refused before cryptographic processing', () async {
    expect(maxBackupPlaintextBytes, 64 * 1024 * 1024);
    expect(maxBackupEnvelopeBytes, maxBackupPlaintextBytes + 112);
    await expectLater(
      sealBackup(
        Uint8List(maxBackupPlaintextBytes + 1),
        'Public fictional test passphrase',
        platform: 'android',
      ),
      throwsA(isA<BackupFailure>()),
    );
    await expectLater(
      openBackup(
        Uint8List(maxBackupEnvelopeBytes + 1),
        'Public fictional test passphrase',
        platform: 'android',
      ),
      throwsA(isA<BackupFailure>()),
    );
  });
  test('full release migration preserves imported records and populated receipts, identity, raw history, cancel and recovery', () async {
    final root = Directory.systemTemp.createTempSync('bhli-release-migration-');
    for (final name in [
      'dev-sandbox',
      'production-sandbox',
      'transfer-recipient',
    ]) {
      Directory('${root.path}/$name').createSync(recursive: true);
    }
    final source = await SqliteOfflineRepository.open(
      '${root.path}/dev-sandbox/source.db',
      factory: databaseFactoryFfi,
      ownership: HostOwnership('${root.path}/dev-sandbox/owner.lock'),
    );
    var target = await SqliteOfflineRepository.open(
      '${root.path}/production-sandbox/target.db',
      factory: databaseFactoryFfi,
      ownership: HostOwnership('${root.path}/production-sandbox/owner.lock'),
    );
    final recipient = await SqliteOfflineRepository.open(
      '${root.path}/transfer-recipient/recipient.db',
      factory: databaseFactoryFfi,
    );
    const password = 'Public fictional rehearsal passphrase only';
    final sourceStore = BackupStore(
      source,
      evidence: FilesEvidence(Directory('${root.path}/source-evidence')),
      scratchFactory: databaseFactoryFfi,
    );
    final targetStore = BackupStore(
      target,
      evidence: FilesEvidence(Directory('${root.path}/target-evidence')),
      scratchFactory: databaseFactoryFfi,
    );
    try {
      final originalProfile = await source.saveProfile(
        'Fictional Original Auditor',
      );
      final a = newUuid(), b = newUuid(), c = newUuid();
      await source.create(a, values('Fictional Driver A'));
      await source.saveProfile('Fictional Renamed Auditor');
      await source.update(a, 1, values('Fictional Edited A'));
      await source.create(b, values('Fictional Archived B'));
      await source.archive(b, 1);
      await source.create(c, values('Fictional Active C'));
      final donor = await SqliteOfflineRepository.open(
        '${root.path}/donor.db',
        factory: databaseFactoryFfi,
      );
      try {
        await donor.saveProfile('Fictional Imported Original Auditor');
        await donor.create(
          newUuid(),
          values('Fictional Previously Imported Driver'),
        );
        final incoming = await donor.exportTransfer();
        await source.applyTransfer(
          incoming,
          await source.previewTransfer(incoming),
        );
      } finally {
        await donor.close();
      }
      final complete = await source.captureBackup();
      expect(complete.rows['audit_records']!.length, 4);
      expect(complete.rows['audit_events']!.length, 6);
      expect(complete.rows['transfer_receipts']!.length, 1);
      expect(complete.metadata['source_version'], offlineBackupSourceVersion);
      final unavailable = FilesEvidence(
        Directory('${root.path}/unavailable-evidence'),
      )..failRetain = true;
      final unavailableStore = BackupStore(
        source,
        evidence: unavailable,
        scratchFactory: databaseFactoryFfi,
      );
      await expectLater(
        unavailableStore.createBackup(password),
        throwsA(isA<FileSystemException>()),
      );
      expect((await source.captureBackup()).rows, complete.rows);
      final archive = await sourceStore.createBackup(password);
      final external = File('${root.path}/external-source.bhlibackup');
      await external.writeAsBytes(archive.bytes, flush: true);
      final encrypted = await external.readAsBytes();
      expect(
        decodeBackupState(
          await openBackup(encrypted, password, platform: 'android'),
          platform: 'android',
        ).digest,
        complete.digest,
      );
      await target.saveProfile('Fictional Target Before Restore');
      await target.create(newUuid(), values('Fictional Preexisting Target'));
      final before = await target.captureBackup();
      await expectLater(
        targetStore.inspectRestore(encrypted, 'incorrect fictional passphrase'),
        throwsA(anything),
      );
      final damaged = Uint8List.fromList(encrypted);
      damaged[damaged.length - 1] ^= 1;
      await expectLater(
        targetStore.inspectRestore(damaged, password),
        throwsA(anything),
      );
      expect((await target.captureBackup()).digest, before.digest);
      Future<PreparedRestore> prepare() async {
        final preview = await targetStore.inspectRestore(encrypted, password);
        return targetStore.prepareRestore(
          preview,
          password,
          publishRecovery: (artifact) async {
            final saved = File('${root.path}/recovery-${newUuid()}.bhlibackup');
            await saved.writeAsBytes(artifact.bytes, flush: true);
            return saved.readAsBytes();
          },
        );
      }

      final failingPreview = await targetStore.inspectRestore(
        encrypted,
        password,
      );
      await expectLater(
        targetStore.prepareRestore(
          failingPreview,
          password,
          publishRecovery: (artifact) async {
            throw const FileSystemException(
              'Injected recovery destination failure',
            );
          },
        ),
        throwsA(isA<FileSystemException>()),
      );
      expect((await target.captureBackup()).rows, before.rows);
      final cancelled = await prepare();
      await targetStore.cancelPrepared(cancelled);
      expect((await target.captureBackup()).digest, before.digest);
      final recovery = await targetStore.createBackup(password);
      final result = await targetStore.applyRestore(await prepare());
      expect(result.outcome, RestoreOutcome.restored);
      final restored = await target.captureBackup();
      expect(restored.rows, complete.rows);
      expect(restored.digest, complete.digest);
      expect(restored.sequence, complete.sequence);
      expect((await target.profile())!.id, originalProfile.id);
      expect(
        (await target.read(a)).auditedByName,
        'Fictional Original Auditor',
      );
      expect((await target.history(a)).length, 2);
      expect((await source.captureBackup()).digest, complete.digest);
      await target.close();
      target = await SqliteOfflineRepository.open(
        '${root.path}/production-sandbox/target.db',
        factory: databaseFactoryFfi,
        ownership: HostOwnership('${root.path}/production-sandbox/owner.lock'),
      );
      expect((await target.captureBackup()).rows, complete.rows);
      final reopenedStore = BackupStore(
        target,
        evidence: FilesEvidence(Directory('${root.path}/target-evidence')),
        scratchFactory: databaseFactoryFfi,
      );
      final rollbackPreview = await reopenedStore.inspectRestore(
        recovery.bytes,
        password,
      );
      final rollbackTicket = await reopenedStore.prepareRestore(
        rollbackPreview,
        password,
        publishRecovery: (a) async {
          final f = File('${root.path}/rollback-safety.bhlibackup');
          await f.writeAsBytes(a.bytes, flush: true);
          return f.readAsBytes();
        },
      );
      expect(
        (await reopenedStore.applyRestore(rollbackTicket)).outcome,
        RestoreOutcome.restored,
      );
      expect((await target.captureBackup()).rows, before.rows);
      // A fresh actual repository may live in another path while retaining logical backup ID.
      final encoded = await openBackup(
        encrypted,
        password,
        platform: 'android',
      );
      final invalidLogical = Uint8List.fromList(
        utf8.encode(
          utf8
              .decode(encoded)
              .replaceAll(
                'com.bhli.audit.offline',
                'com.bhli.audit.production',
              ),
        ),
      );
      expect(
        () => decodeBackupState(invalidLogical, platform: 'android'),
        throwsA(anything),
      );
      await recipient.saveProfile('Fictional Independent Recipient');
      final recipientId = (await recipient.profile())!.id;
      final transfer = await source.exportTransfer();
      final preview = await recipient.previewTransfer(transfer);
      expect(preview.newIds.length, 4);
      await recipient.applyTransfer(transfer, preview);
      expect((await recipient.profile())!.id, recipientId);
      expect(recipientId, isNot(originalProfile.id));
      expect(
        (await recipient.read(a)).auditedByName,
        'Fictional Original Auditor',
      );
      expect((await recipient.history(a)).length, 2);
      final repeat = await recipient.previewTransfer(transfer);
      expect(repeat.newIds, isEmpty);
      expect(repeat.duplicateIds.length, 4);
      await recipient.applyTransfer(transfer, repeat);
      expect(
        (await recipient.captureBackup()).rows['audit_records']!.length,
        4,
      );
      expect((await recipient.captureBackup()).rows['audit_events']!.length, 6);
      final importedState = await recipient.captureBackup();
      List<Map<String, Object?>> sortedRows(
        BackupState state,
        String table, {
        bool stripSequence = false,
      }) {
        final rows = state.rows[table]!
            .map((r) => Map<String, Object?>.from(r))
            .toList();
        if (stripSequence) {
          for (final row in rows) {
            row.remove('seq');
          }
        }
        if (table == 'audit_events') {
          for (final row in rows) {
            for (final key in ['before_json', 'after_json']) {
              if (row[key] != null) row[key] = jsonDecode(row[key] as String);
            }
          }
        }
        rows.sort((a, b) => (a['id'] as String).compareTo(b['id'] as String));
        return rows;
      }

      expect(
        sortedRows(importedState, 'audit_records', stripSequence: true),
        sortedRows(complete, 'audit_records', stripSequence: true),
      );
      expect(
        sortedRows(importedState, 'audit_events'),
        sortedRows(complete, 'audit_events'),
      );
    } finally {
      await source.close();
      await target.close();
      await recipient.close();
      assert(root.parent.absolute.path == Directory.systemTemp.absolute.path);
      await root.delete(recursive: true);
    }
  }, timeout: const Timeout(Duration(minutes: 5)));
}
