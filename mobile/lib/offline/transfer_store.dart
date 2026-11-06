import 'dart:convert';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:sqflite/sqflite.dart';

import 'models.dart';
import 'transfer.dart';

abstract class OfflineTransferRepository {
  Future<Uint8List> exportTransfer({
    String? dateFrom,
    String? dateTo,
    bool Function()? cancel,
  });
  Future<ImportPreview> previewTransfer(Uint8List raw);
  Future<ImportResult> applyTransfer(
    Uint8List raw,
    ImportPreview preview, {
    bool Function()? cancel,
  });
}

class ImportPreview {
  ImportPreview({
    required this.contentSha256,
    required List<String> newIds,
    required List<String> duplicateIds,
    required List<String> conflictIds,
  }) : newIds = List.unmodifiable(newIds),
       duplicateIds = List.unmodifiable(duplicateIds),
       conflictIds = List.unmodifiable(conflictIds);
  final String contentSha256;
  final List<String> newIds, duplicateIds, conflictIds;
}

class ImportResult {
  const ImportResult({
    required this.imported,
    required this.duplicates,
    required this.conflicts,
  });
  final int imported, duplicates, conflicts;
}

Never _invalid() => throw const OfflineFailure(
  'validation',
  'This transfer file is invalid or exceeds transfer limits. Narrow the export date range and retry.',
);
Never _conflict(String message) => throw OfflineFailure('conflict', message);
void _canceled(bool Function()? cancel) {
  if (cancel?.call() ?? false) {
    throw const OfflineFailure(
      'canceled',
      'Transfer canceled before completion. Check records before retrying if completion was interrupted.',
    );
  }
}

/// Freeze at admission, before the repository queue can yield to its caller.
Uint8List freezeTransferBytes(Uint8List raw) {
  if (raw.length > 32 * 1024 * 1024) _invalid();
  return Uint8List.fromList(raw).asUnmodifiableView();
}

Future<TransferPackage> _decode(Uint8List raw) async {
  try {
    return await Isolate.run(() => decodeTransfer(raw));
  } on FormatException {
    _invalid();
  }
}

// Keep the isolate closure outside the transaction's lexical scope. In
// particular, cancellation can capture a Widget State that is not sendable.
Future<Uint8List> _encode(
  Map<String, dynamic> manifest,
  List<Map<String, dynamic>> audits,
  List<Map<String, dynamic>> events,
) => Isolate.run(() => encodeTransfer(manifest, audits, events));

String _timestamp(Object? value) {
  if (value is! String) _invalid();
  final time = DateTime.tryParse(value);
  if (time == null || !RegExp(r'(Z|[+-][0-9]{2}:[0-9]{2})$').hasMatch(value)) {
    _invalid();
  }
  final utc = time.toUtc();
  if (utc.year < 1000 || utc.year > 9999) _invalid();
  final iso = utc.toIso8601String();
  final dot = iso.indexOf('.');
  final fraction = iso.substring(dot + 1, iso.length - 1).padRight(6, '0');
  return '${iso.substring(0, dot)}.${fraction}Z';
}

Map<String, dynamic> _audit(Map<String, Object?> row) {
  final result = Map<String, dynamic>.from(row)..remove('seq');
  for (final key in ['created_at', 'updated_at', 'archived_at']) {
    if (result[key] != null) result[key] = _timestamp(result[key]);
  }
  return result;
}

Map<String, dynamic> _event(Map<String, Object?> row) => {
  for (final key in [
    'id',
    'audit_id',
    'revision',
    'action',
    'actor_name',
    'actor_profile_id',
  ])
    key: row[key],
  'created_at': _timestamp(row['created_at']),
  'before': row['before_json'] == null
      ? null
      : _audit(
          Map<String, Object?>.from(
            jsonDecode(row['before_json'] as String) as Map,
          ),
        ),
  'after': _audit(
    Map<String, Object?>.from(jsonDecode(row['after_json'] as String) as Map),
  ),
};

class _Budget {
  int bytes = 0;
  void add(Map<String, dynamic> row) {
    final length = canonicalJson(row).length + 1; // Canonical output is ASCII.
    if (length > 262144 || bytes + length > 32 * 1024 * 1024) _invalid();
    bytes += length;
  }
}

Future<List<Map<String, dynamic>>> _events(
  Transaction txn,
  String id, {
  bool Function()? cancel,
  _Budget? budget,
  int remaining = 10000,
}) async {
  final result = <Map<String, dynamic>>[];
  for (var offset = 0; ; offset += 50) {
    _canceled(cancel);
    final rows = await txn.query(
      'audit_events',
      where: 'audit_id = ?',
      whereArgs: [id],
      orderBy: 'revision',
      limit: 50,
      offset: offset,
    );
    for (final row in rows) {
      if (result.length >= remaining) _invalid();
      final event = _event(row);
      budget?.add(event);
      result.add(event);
    }
    if (rows.length < 50) return result;
  }
}

/// Called only inside the repository's existing admitted-operation transaction.
Future<Uint8List> exportTransferTransaction(
  Transaction txn, {
  String? dateFrom,
  String? dateTo,
  bool Function()? cancel,
}) async {
  if ((dateFrom != null && !validOfflineDate(dateFrom)) ||
      (dateTo != null && !validOfflineDate(dateTo)) ||
      (dateFrom != null && dateTo != null && dateFrom.compareTo(dateTo) > 0)) {
    _invalid();
  }
  _canceled(cancel);
  final clauses = <String>[], args = <Object?>[];
  if (dateFrom != null) {
    clauses.add('audit_date >= ?');
    args.add(dateFrom);
  }
  if (dateTo != null) {
    clauses.add('audit_date <= ?');
    args.add(dateTo);
  }
  final audits = <Map<String, dynamic>>[], events = <Map<String, dynamic>>[];
  final budget = _Budget();
  for (var offset = 0; ; offset += 50) {
    _canceled(cancel);
    final rows = await txn.query(
      'audit_records',
      where: clauses.isEmpty ? null : clauses.join(' AND '),
      whereArgs: args,
      orderBy: 'id',
      limit: 50,
      offset: offset,
    );
    for (final row in rows) {
      _canceled(cancel);
      if (audits.length >= 2000) _invalid();
      final audit = _audit(row);
      budget.add(audit);
      audits.add(audit);
      events.addAll(
        await _events(
          txn,
          row['id'] as String,
          cancel: cancel,
          budget: budget,
          remaining: 10000 - events.length,
        ),
      );
    }
    if (rows.length < 50) break;
  }
  final installation = (await txn.query(
    'app_meta',
    columns: ['value'],
    where: 'key = ?',
    whereArgs: ['installation_id'],
  )).single['value'];
  final manifest = <String, dynamic>{
    'format': 'bhli-audit-transfer',
    'format_version': 1,
    'package_id': newUuid(),
    'source_installation_id': installation,
    'exported_at': _timestamp(DateTime.now().toUtc().toIso8601String()),
    'filters': {
      'date_from': dateFrom,
      'date_to': dateTo,
      'include_archived': true,
    },
  };
  _canceled(cancel);
  try {
    final result = await _encode(manifest, audits, events);
    _canceled(cancel);
    return result;
  } on FormatException {
    _invalid();
  }
}

bool _sameIds(List<String> a, List<String> b) =>
    a.length == b.length &&
    Iterable<int>.generate(a.length).every((i) => a[i] == b[i]);

Future<ImportPreview> _classify(
  Transaction txn,
  TransferPackage package, {
  bool Function()? cancel,
}) async {
  final receipt = await txn.query(
    'transfer_receipts',
    columns: ['content_sha256'],
    where: 'package_id = ?',
    whereArgs: [package.manifest['package_id']],
  );
  if (receipt.isNotEmpty &&
      receipt.single['content_sha256'] != package.contentSha256) {
    _conflict(
      'This package identity was already used for different content. Nothing was imported.',
    );
  }
  final histories = <String, List<Map<String, dynamic>>>{};
  for (final event in package.events) {
    _canceled(cancel);
    histories.putIfAbsent(event['audit_id'] as String, () => []).add(event);
    final resident = await txn.query(
      'audit_events',
      where: 'id = ?',
      whereArgs: [event['id']],
    );
    if (resident.isNotEmpty &&
        canonicalJson(_event(resident.single)) != canonicalJson(event)) {
      _conflict(
        'This file contains a history identity already used for different content. Nothing was imported.',
      );
    }
  }
  final added = <String>[], duplicate = <String>[], conflict = <String>[];
  for (final audit in package.audits) {
    _canceled(cancel);
    final id = audit['id'] as String;
    final resident = await txn.query(
      'audit_records',
      where: 'id = ?',
      whereArgs: [id],
    );
    if (resident.isEmpty) {
      added.add(id);
    } else if (canonicalJson(_audit(resident.single)) == canonicalJson(audit) &&
        canonicalJson(
              await _events(txn, id, cancel: cancel, budget: _Budget()),
            ) ==
            canonicalJson(histories[id])) {
      duplicate.add(id);
    } else {
      conflict.add(id);
    }
  }
  return ImportPreview(
    contentSha256: package.contentSha256,
    newIds: added,
    duplicateIds: duplicate,
    conflictIds: conflict,
  );
}

Future<ImportPreview> previewTransferTransaction(
  Transaction txn,
  Uint8List raw,
) async => _classify(txn, await _decode(raw));

Future<ImportResult> applyTransferTransaction(
  Transaction txn,
  Uint8List raw,
  ImportPreview preview, {
  bool Function()? cancel,
}) async {
  _canceled(cancel);
  final package = await _decode(raw);
  final current = await _classify(txn, package, cancel: cancel);
  if (preview.contentSha256 != current.contentSha256 ||
      !_sameIds(preview.newIds, current.newIds) ||
      !_sameIds(preview.duplicateIds, current.duplicateIds) ||
      !_sameIds(preview.conflictIds, current.conflictIds)) {
    _conflict(
      'Local audits changed after preview. Review the file again before importing.',
    );
  }
  final selected = current.newIds.toSet();
  for (final audit in package.audits) {
    if (!selected.contains(audit['id'])) continue;
    _canceled(cancel);
    await txn.insert('auditor_identities', {
      'id': audit['profile_id'],
    }, conflictAlgorithm: ConflictAlgorithm.ignore);
    await txn.insert('audit_records', Map<String, Object?>.from(audit));
  }
  for (final event in package.events) {
    if (!selected.contains(event['audit_id'])) continue;
    _canceled(cancel);
    await txn.insert('auditor_identities', {
      'id': event['actor_profile_id'],
    }, conflictAlgorithm: ConflictAlgorithm.ignore);
    await txn.insert('audit_events', {
      for (final key in [
        'id',
        'audit_id',
        'revision',
        'action',
        'actor_name',
        'actor_profile_id',
        'created_at',
      ])
        key: event[key],
      'before_json': event['before'] == null
          ? null
          : canonicalJson(event['before']),
      'after_json': canonicalJson(event['after']),
    });
  }
  _canceled(cancel);
  await txn.rawInsert(
    'INSERT INTO transfer_receipts(package_id,content_sha256,source_installation_id,imported_at,imported_count) VALUES (?,?,?,?,?) ON CONFLICT(package_id) DO NOTHING',
    [
      package.manifest['package_id'],
      package.contentSha256,
      package.manifest['source_installation_id'],
      _timestamp(DateTime.now().toUtc().toIso8601String()),
      selected.length,
    ],
  );
  if ((await txn.rawQuery('PRAGMA foreign_key_check')).isNotEmpty) _invalid();
  _canceled(cancel);
  return ImportResult(
    imported: current.newIds.length,
    duplicates: current.duplicateIds.length,
    conflicts: current.conflictIds.length,
  );
}
