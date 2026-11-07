import 'dart:async';
import 'dart:convert';
import 'dart:isolate';

import 'package:crypto/crypto.dart';

import 'dart:typed_data';

import 'package:sqflite/sqflite.dart';

import 'backup_state.dart';
import 'backup_crypto.dart';
import 'backup_sqlite.dart';
import 'models.dart';
import 'schema.dart';

class BackupStoreFailure implements Exception {
  const BackupStoreFailure(this.code, this.message);
  final String code, message;
  @override
  String toString() => message;
}

const backupOwnedColumns = <String, String>{
  'app_meta': 'key value',
  'local_profile': 'singleton id name',
  'auditor_identities': 'id',
  'audit_records': 'seq id profile_id driver_name helper_name audit_date station plate_number remarks audited_by_name created_at updated_at revision archived_at',
  'audit_events': 'id audit_id revision action actor_name actor_profile_id created_at before_json after_json',
  'transfer_receipts': 'package_id content_sha256 source_installation_id imported_at imported_count',
};
const _rowLimits = <String, int>{
  'app_meta': 2,
  'local_profile': 1,
  'auditor_identities': 40001,
  'audit_records': 20000,
  'audit_events': 100000,
  'transfer_receipts': 20000,
};
const _deleteOrder = [
  'audit_events',
  'transfer_receipts',
  'audit_records',
  'local_profile',
  'auditor_identities',
  'app_meta',
];

Never _invalid() => throw const BackupStoreFailure(
  'state',
  'The complete local state could not be verified. Nothing was restored.',
);
void _need(bool condition) {
  if (!condition) _invalid();
}

String _creationTime() {
  final now = DateTime.now().toUtc();
  return '${now.toIso8601String().split('.').first}.${(now.millisecond * 1000 + now.microsecond).toString().padLeft(6, '0')}Z';
}

// A top-level isolate boundary deliberately captures only detached row values,
// never the sqflite Transaction/Database or its native platform messenger.
Future<BackupState> _detachedState(
  Map<String, List<Map<String, Object?>>> rows,
  int? sequence,
) => Isolate.run(
  () => decodeBackupState(
    encodeBackupState(
      rows,
      platform: 'android',
      sequence: sequence,
      backupId: newUuid(),
      createdAt: _creationTime(),
      sourceVersion: '1.0.0+2',
    ),
    platform: 'android',
  ),
);

/// Owner-transaction-only complete snapshot; no filtered public listing calls.
Future<BackupState> captureBackupTransaction(Transaction txn) async {
  // Reject oversized stores through SQLite scalar results before materializing
  // even metadata. No row or raw history string may bypass the payload ceiling.
  var rawBytes = 0;
  final counts = <String, int>{};
  for (final entry in backupOwnedColumns.entries) {
    final size = entry.value
        .split(' ')
        .map((column) => 'COALESCE(length(CAST($column AS BLOB)),0)')
        .join('+');
    final bounds = (await txn.rawQuery(
      'SELECT COUNT(*) AS n,COALESCE(SUM($size),0) AS bytes,COALESCE(MAX($size),0) AS largest FROM ${entry.key}',
    )).single;
    final count = bounds['n'] as int;
    rawBytes += bounds['bytes'] as int;
    _need(
      count <= _rowLimits[entry.key]! &&
          rawBytes <= maxBackupPlaintextBytes &&
          (bounds['largest'] as int) <= 1024 * 1024,
    );
    counts[entry.key] = count;
  }
  await verifyOfflineSchema(txn, 2);
  _need((await txn.rawQuery('PRAGMA user_version')).single.values.single == 2);
  _need((await txn.rawQuery('PRAGMA foreign_keys')).single.values.single == 1);
  final rows = <String, List<Map<String, Object?>>>{};
  var encodedBytes = 0;
  const order = {
    'app_meta': 'key',
    'local_profile': 'singleton',
    'auditor_identities': 'id',
    'audit_records': 'seq',
    'audit_events': 'audit_id,revision',
    'transfer_receipts': 'package_id',
  };
  for (final entry in backupOwnedColumns.entries) {
    final collected = <Map<String, Object?>>[];
    for (var offset = 0; offset < counts[entry.key]!; offset += 16) {
      final page = await txn.query(
        entry.key,
        columns: entry.value.split(' '),
        orderBy: order[entry.key],
        limit: 16,
        offset: offset,
      );
      _need(page.isNotEmpty);
      for (final row in page) {
        final encoded = jsonEncode({'kind': entry.key, 'row': row});
        var lineBytes = 1;
        for (final code in encoded.codeUnits) {
          lineBytes += code > 126 ? 6 : 1;
        }
        encodedBytes += lineBytes;
        _need(
          lineBytes <= 1024 * 1024 && encodedBytes <= maxBackupPlaintextBytes,
        );
        collected.add(row);
      }
    }
    _need(collected.length == counts[entry.key]);
    rows[entry.key] = collected;
  }
  final watermark = await txn.query(
    'sqlite_sequence',
    columns: ['seq'],
    where: 'name = ?',
    whereArgs: ['audit_records'],
  );
  _need(watermark.length <= 1);
  final sequence = watermark.isEmpty ? null : watermark.single['seq'];
  _need(sequence == null || sequence is int);
  _need(
    (await txn.rawQuery('PRAGMA integrity_check')).single.values.single == 'ok',
  );
  return _detachedState(rows, sequence as int?);
}

Uint8List encodeCapturedBackup(BackupState state) => encodeBackupState(
  state.rows,
  platform: 'android',
  sequence: state.sequence,
  backupId: state.metadata['backup_id'] as String,
  createdAt: state.metadata['created_at'] as String,
  sourceVersion: state.metadata['source_version'] as String,
);

/// The caller owns one reserved transaction and checked COMMIT/outcome handling.
/// All SQL identifiers originate in the built-in fixed schema above.
Future<void> replaceBackupTransaction(
  Transaction txn,
  BackupState candidate,
  String expectedCurrentDigest, {
  bool Function()? cancel,
}) async {
  void check() {
    if (cancel?.call() == true) {
      throw const BackupStoreFailure(
        'cancelled',
        'Replacement was cancelled before COMMIT.',
      );
    }
  }

  check();
  final current = await captureBackupTransaction(txn);
  if (current.digest != expectedCurrentDigest) {
    throw const BackupStoreFailure(
      'stale',
      'Local data changed. Inspect and protect a fresh preview before replacing it.',
    );
  }
  final verified = await _detachedState(candidate.rows, candidate.sequence);
  _need(candidate.platform == 'android' && verified.digest == candidate.digest);
  for (final table in _deleteOrder) {
    check();
    await txn.delete(table);
  }
  for (final entry in backupOwnedColumns.entries) {
    final columns = entry.value.split(' ');
    final sql =
        'INSERT INTO ${entry.key} (${columns.join(',')}) VALUES (${List.filled(columns.length, '?').join(',')})';
    for (final row in verified.rows[entry.key]!) {
      check();
      await txn.rawInsert(sql, [for (final column in columns) row[column]]);
    }
  }
  await txn.delete(
    'sqlite_sequence',
    where: 'name = ?',
    whereArgs: ['audit_records'],
  );
  if (verified.sequence != null) {
    await txn.rawInsert('INSERT INTO sqlite_sequence (name,seq) VALUES (?,?)', [
      'audit_records',
      verified.sequence,
    ]);
  }
  check();
  _need((await captureBackupTransaction(txn)).digest == verified.digest);
  check();
}

// Application owner interface keeps native connections out of restore/UI code.
abstract interface class OfflineRecoveryStatus {
  RestoreResult? get startupRecovery;
}

abstract interface class OfflineBackupRepository {
  Future<BackupState> captureBackup();
  Future<T> withBackupMaintenance<T>(
    Future<T> Function(BackupMaintenance owner) work,
  );
}

abstract interface class BackupMaintenance {
  Future<void> checkOwnership();
  Future<BackupState> capture();
  Future<void> replace(
    BackupState candidate,
    String expectedDigest, {
    bool Function()? cancel,
  });
  Future<BackupState> reopen();
  void blockWrites();
  void advanceGeneration();
}

abstract interface class BackupEvidence {
  /// Returns a generated private retained filename after file/directory sync.
  Future<String> retain(Uint8List envelope);
  Future<Uint8List> read(String handle);
  Future<Uint8List?> readMarker();
  Future<void> writeMarker(Uint8List bytes);
  Future<void> clearMarker();
}

class BackupArtifact {
  BackupArtifact._(this.handle, Uint8List bytes, this.state)
    : _bytes = Uint8List.fromList(bytes);
  final String handle;
  final Uint8List _bytes;
  final BackupState state;
  Uint8List get bytes => Uint8List.fromList(_bytes);
}

class RestorePreview {
  RestorePreview._(this.candidate, this.current, this._artifact);
  final BackupState candidate, current;
  final BackupArtifact _artifact;
  bool get unchanged => candidate.digest == current.digest;
}

class PreparedRestore {
  PreparedRestore._(this.preview);
  final RestorePreview preview;
}

enum RestoreOutcome { original, restored, unknown }

class RestoreResult {
  const RestoreResult(this.outcome, {this.warning = ''});
  final RestoreOutcome outcome;
  final String warning;
}

class _Pending {
  _Pending(this.ticket);
  final PreparedRestore ticket;
  final ready = Completer<PreparedRestore>();
  final decision = Completer<bool>();
  late Future<RestoreResult> result;
  bool cancelRequested = false;
  _BackupControl? applying;
}

const assistedAndroidRecovery =
    'Preserve this installation, its database, sidecars and encrypted recovery files. '
    'Close other offline copies and older versions before Retry. If storage stays unreadable, '
    'use a verified encrypted backup on a separate Android device or supported OS user '
    'with the normal app sandbox. Protect that fresh target using the normal restore workflow. '
    'Keep the damaged original for assisted recovery and retire duplicate active identities. '
    'Do not clear data, uninstall, overwrite or move the damaged original. '
    'A lost backup password cannot be reset. Changes made after your last backup '
    'might be unrecoverable. SQLite journal files may change during recovery or close; '
    'the app will not automatically delete or reset the database.';

Future<Uint8List> _encodeDetached(BackupState state) =>
    Isolate.run(() => encodeCapturedBackup(state));

String _hash(List<int> bytes) => sha256.convert(bytes).toString();
final _evidenceName = RegExp(
  r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.bhlibackup$',
);
const _markerKeys = [
  'app_id',
  'input_digest',
  'input_file',
  'intended_digest',
  'operation_id',
  'original_digest',
  'platform',
  'recovery_digest',
  'recovery_file',
  'stage',
  'version',
];
Uint8List _markerBytes(Map<String, Object?> marker) => Uint8List.fromList(
  ascii.encode(
    '${jsonEncode({for (final key in _markerKeys) key: marker[key]})}\n',
  ),
);
Future<Map<String, Object?>> _verifiedMarker(
  BackupEvidence evidence,
  Uint8List raw,
) async {
  _need(raw.isNotEmpty && raw.length <= 4096);
  final decoded = jsonDecode(ascii.decode(raw));
  _need(
    decoded is Map &&
        decoded.length == _markerKeys.length &&
        _markerKeys.every(decoded.containsKey),
  );
  final marker = Map<String, Object?>.from(decoded as Map);
  _need(_hash(_markerBytes(marker)) == _hash(raw));
  _need(
    marker['version'] is int &&
        marker['version'] == 1 &&
        marker['platform'] == 'android' &&
        marker['app_id'] == 'com.bhli.audit.offline' &&
        marker['stage'] == 'pending',
  );
  _need(
    marker['operation_id'] is String &&
        validOfflineUuid(marker['operation_id'] as String),
  );
  for (final key in [
    'original_digest',
    'intended_digest',
    'input_digest',
    'recovery_digest',
  ]) {
    _need(
      marker[key] is String &&
          RegExp(r'^[0-9a-f]{64}$').hasMatch(marker[key] as String),
    );
  }
  _need(marker['input_file'] != marker['recovery_file']);
  for (final prefix in ['input', 'recovery']) {
    final name = marker['${prefix}_file'];
    _need(name is String && _evidenceName.hasMatch(name));
    final bytes = await evidence.read(name as String);
    _need(
      bytes.length <= maxBackupEnvelopeBytes &&
          _hash(bytes) == marker['${prefix}_digest'],
    );
  }
  return marker;
}

/// Startup invokes this while holding lifetime ownership, before UI admission.
/// Markers describe evidence, never authorize replay or unattended decryption.
Future<RestoreResult?> reconcileBackupStartup(
  BackupMaintenance owner,
  BackupEvidence evidence, {
  bool reopen = false,
}) async {
  try {
    await owner.checkOwnership();
    final raw = await evidence.readMarker();
    if (raw == null) return null;
    final marker = await _verifiedMarker(evidence, raw);
    final state = await (reopen ? owner.reopen() : owner.capture());
    final RestoreOutcome outcome;
    if (state.digest == marker['intended_digest']) {
      outcome = RestoreOutcome.restored;
      owner.advanceGeneration();
    } else if (state.digest == marker['original_digest']) {
      outcome = RestoreOutcome.original;
    } else {
      owner.blockWrites();
      return const RestoreResult(
        RestoreOutcome.unknown,
        warning: assistedAndroidRecovery,
      );
    }
    var warning = '';
    try {
      await evidence.clearMarker();
    } catch (_) {
      owner.blockWrites();
      warning = 'The complete outcome is verified, but its recovery marker could not be cleared. Local changes stay blocked. Retain all encrypted evidence.';
    }
    return RestoreResult(outcome, warning: warning);
  } catch (_) {
    owner.blockWrites();
    return const RestoreResult(
      RestoreOutcome.unknown,
      warning: assistedAndroidRecovery,
    );
  }
}

class _BackupControl {
  _BackupControl(this.cancel);
  final bool Function()? cancel;
  final watch = Stopwatch()..start();
  bool get stopped =>
      cancel?.call() == true || watch.elapsed > const Duration(minutes: 10);
  void check() {
    if (stopped) {
      throw const BackupStoreFailure(
        'cancelled',
        'Backup operation cancelled or exceeded its safe time limit.',
      );
    }
  }
}

/// Authenticated artifact preparation and one-use final-confirmation tickets.
/// A UI cannot substitute a boolean for durable authenticated recovery proof.
class BackupStore {
  BackupStore(this.repository, {required this.evidence, this.scratchFactory});
  final OfflineBackupRepository repository;
  final BackupEvidence evidence;
  final DatabaseFactory? scratchFactory;
  final _previews = <RestorePreview>{};
  _Pending? _pending;

  Future<BackupState> _unlockState(
    Uint8List encrypted,
    String password,
    _BackupControl control,
  ) async {
    control.check();
    final plain = await openBackup(encrypted, password, platform: 'android');
    control.check();
    final state = await inspectBackupSqlite(plain, factory: scratchFactory);
    control.check();
    return state;
  }

  Future<Uint8List> _sealState(
    BackupState state,
    String password,
    _BackupControl control,
  ) async {
    control.check();
    final plain = await _encodeDetached(state);
    control.check();
    final envelope = await sealBackup(plain, password, platform: 'android');
    control.check();
    return envelope;
  }

  Future<BackupArtifact> _retainVerified(
    Uint8List envelope,
    String password,
    String expectedDigest,
    _BackupControl control,
  ) async {
    control.check();
    _need(envelope.length <= maxBackupEnvelopeBytes);
    final handle = await evidence.retain(envelope);
    control.check();
    _need(_evidenceName.hasMatch(handle));
    final readback = await evidence.read(handle);
    control.check();
    _need(_hash(readback) == _hash(envelope));
    final state = await _unlockState(readback, password, control);
    control.check();
    _need(state.digest == expectedDigest);
    return BackupArtifact._(handle, readback, state);
  }

  Future<BackupArtifact> createBackup(
    String password, {
    bool Function()? cancel,
  }) async {
    final control = _BackupControl(cancel)..check();
    final state = await repository.captureBackup();
    control.check();
    final envelope = await _sealState(state, password, control);
    return _retainVerified(envelope, password, state.digest, control);
  }

  Future<RestorePreview> inspectRestore(
    Uint8List encrypted,
    String password, {
    bool Function()? cancel,
  }) async {
    if (_pending != null) {
      throw const BackupStoreFailure(
        'maintenance',
        'Finish the pending recovery operation first.',
      );
    }
    _previews.clear();
    final control = _BackupControl(cancel)..check();
    _need(encrypted.length <= maxBackupEnvelopeBytes);
    final frozen = Uint8List.fromList(encrypted);
    final candidate = await _unlockState(frozen, password, control);
    control.check();
    final input = await _retainVerified(
      frozen,
      password,
      candidate.digest,
      control,
    );
    final current = await repository.captureBackup();
    final preview = RestorePreview._(candidate, current, input);
    control.check();
    if (!preview.unchanged) _previews.add(preview);
    return preview;
  }

  void cancelPreview(RestorePreview preview) {
    _previews.remove(preview);
  }

  Future<PreparedRestore> prepareRestore(
    RestorePreview preview,
    String password, {
    required Future<Uint8List> Function(BackupArtifact recovery)
    publishRecovery,
    bool Function()? cancel,
  }) async {
    if (_pending != null || !_previews.remove(preview) || preview.unchanged) {
      throw const BackupStoreFailure(
        'preview',
        'Inspect a changed backup before preparing replacement.',
      );
    }
    final control = _BackupControl(cancel)..check();
    final pending = _Pending(PreparedRestore._(preview));
    _pending = pending;
    pending.result = repository.withBackupMaintenance((owner) async {
      var markerAttempted = false;
      try {
        control.check();
        await owner.checkOwnership();
        if (await evidence.readMarker() != null) {
          throw const BackupStoreFailure(
            'pending',
            'Resolve the pending recovery operation first.',
          );
        }
        final current = await owner.capture();
        if (current.digest != preview.current.digest) {
          throw const BackupStoreFailure(
            'stale',
            'Local data changed. Inspect a fresh preview.',
          );
        }
        // Re-authenticate the frozen incoming artifact with the supplied password.
        final incoming = await evidence.read(preview._artifact.handle);
        _need(_hash(incoming) == _hash(preview._artifact._bytes));
        final candidate = await _unlockState(incoming, password, control);
        _need(candidate.digest == preview.candidate.digest);
        control.check();
        final recovery = await _retainVerified(
          await _sealState(current, password, control),
          password,
          current.digest,
          control,
        );
        control.check();
        final published = await publishRecovery(recovery);
        control.check();
        _need(
          published.length <= maxBackupEnvelopeBytes &&
              _hash(published) == _hash(recovery._bytes),
        );
        final publicState = await _unlockState(published, password, control);
        _need(publicState.digest == current.digest);
        // No password/key is stored in the opaque ticket or marker.
        control.check();
        password = '';
        pending.ready.complete(pending.ticket);
        if (!await pending.decision.future || pending.cancelRequested) {
          return const RestoreResult(RestoreOutcome.original);
        }
        pending.applying!.check();
        await owner.checkOwnership();
        final marker = <String, Object?>{
          'version': 1,
          'operation_id': newUuid(),
          'platform': 'android',
          'app_id': 'com.bhli.audit.offline',
          'original_digest': current.digest,
          'intended_digest': candidate.digest,
          'input_file': preview._artifact.handle,
          'input_digest': _hash(incoming),
          'recovery_file': recovery.handle,
          'recovery_digest': _hash(recovery._bytes),
          'stage': 'pending',
        };
        // A marker failure is before BEGIN; it never proceeds to replacement.
        markerAttempted = true;
        await evidence.writeMarker(_markerBytes(marker));
        await _verifiedMarker(evidence, (await evidence.readMarker())!);
        try {
          await owner.replace(
            candidate,
            current.digest,
            cancel: () => pending.cancelRequested || pending.applying!.stopped,
          );
        } catch (_) {
          // sqflite owns rollback on transaction error. Lost COMMIT ack is still
          // classified by reopened complete state; never retry or reverse it.
        }
        final outcome = await reconcileBackupStartup(
          owner,
          evidence,
          reopen: true,
        );
        if (outcome == null) {
          owner.blockWrites();
          return const RestoreResult(
            RestoreOutcome.unknown,
            warning: assistedAndroidRecovery,
          );
        }
        return outcome;
      } catch (error, stack) {
        if (markerAttempted) {
          try {
            if (await evidence.readMarker() != null) owner.blockWrites();
          } catch (_) {
            owner.blockWrites();
          }
        }
        if (!pending.ready.isCompleted) {
          pending.ready.completeError(error, stack);
        }
        rethrow;
      } finally {
        if (identical(_pending, pending)) _pending = null;
      }
    });
    // Observe early failures even when no final ticket can ever be returned.
    unawaited(
      pending.result.then<void>(
        (_) {},
        onError: (Object error, StackTrace stack) {
          if (!pending.ready.isCompleted) {
            pending.ready.completeError(error, stack);
          }
          if (identical(_pending, pending)) _pending = null;
        },
      ),
    );
    return pending.ready.future;
  }

  Future<RestoreResult> applyRestore(PreparedRestore ticket) {
    final pending = _pending;
    if (pending == null ||
        !identical(pending.ticket, ticket) ||
        pending.decision.isCompleted) {
      return Future.error(
        const BackupStoreFailure(
          'ticket',
          'A fresh prepared confirmation is required.',
        ),
      );
    }
    pending.applying = _BackupControl(null);
    pending.decision.complete(true);
    return pending.result;
  }

  void requestCancel(PreparedRestore ticket) {
    final pending = _pending;
    if (pending == null || !identical(pending.ticket, ticket)) return;
    pending.cancelRequested = true;
    if (!pending.decision.isCompleted) pending.decision.complete(false);
  }

  Future<void> cancelPrepared(PreparedRestore ticket) async {
    final pending = _pending;
    if (pending == null ||
        !identical(pending.ticket, ticket) ||
        pending.decision.isCompleted) {
      throw const BackupStoreFailure(
        'ticket',
        'A fresh prepared confirmation is required.',
      );
    }
    pending.decision.complete(false);
    await pending.result;
  }
}
