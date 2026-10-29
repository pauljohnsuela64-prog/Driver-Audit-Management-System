import 'dart:math';

import '../../core/network/api_failure.dart';
import '../../core/network/json_contract.dart';

const _limits = {
  'driver_name': 200,
  'helper_name': 200,
  'station': 150,
  'plate_number': 30,
  'remarks': 10000,
};
const _keys = {
  'driver_name',
  'helper_name',
  'audit_date',
  'station',
  'plate_number',
  'remarks',
};
const _optional = {'helper_name', 'remarks'};
final _whiteSpace = RegExp(
  r'^[\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$',
);
final _pythonWhiteSpace = RegExp(
  r'^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$',
);

Object? _normalize(String key, Object? value) {
  if (value == null && _optional.contains(key)) return null;
  if (value is! String) throw ApiFailure.invalidInput;
  if (key == 'audit_date') {
    if (!validCalendarDate(value)) throw ApiFailure.invalidInput;
    return value;
  }
  final optional = _optional.contains(key);
  final normalized = value.replaceAll(
    optional ? _pythonWhiteSpace : _whiteSpace,
    '',
  );
  if (normalized.isEmpty) {
    if (optional) return null;
    throw ApiFailure.invalidInput;
  }
  if (normalized.runes.length > _limits[key]!) throw ApiFailure.invalidInput;
  return normalized;
}

Map<String, Object?> _validate(Object? value, {required bool patch}) {
  if (value is! Map ||
      value.isEmpty ||
      value.keys.any((key) => !_keys.contains(key)) ||
      (!patch && value.length != 6)) {
    throw ApiFailure.invalidInput;
  }
  return Map.unmodifiable({
    for (final entry in value.entries)
      entry.key as String: _normalize(entry.key as String, entry.value),
  });
}

/// A normalized, in-memory six-field audit value without server-owned metadata.
class AuditDraft {
  AuditDraft._(this._payload);
  factory AuditDraft({
    required String driverName,
    required String auditDate,
    required String station,
    required String plateNumber,
    String? helperName,
    String? remarks,
  }) => AuditDraft.fromJson({
    'driver_name': driverName,
    'helper_name': helperName,
    'audit_date': auditDate,
    'station': station,
    'plate_number': plateNumber,
    'remarks': remarks,
  });
  factory AuditDraft.fromJson(Object? value) =>
      AuditDraft._(_validate(value, patch: false));
  final Map<String, Object?> _payload;
  String get driverName => _payload['driver_name'] as String;
  String? get helperName => _payload['helper_name'] as String?;
  String get auditDate => _payload['audit_date'] as String;
  String get station => _payload['station'] as String;
  String get plateNumber => _payload['plate_number'] as String;
  String? get remarks => _payload['remarks'] as String?;
  Map<String, Object?> toCreateJson() => _payload;
  Map<String, Object?> diff(AuditDraft baseline) {
    final changed = {
      for (final entry in _payload.entries)
        if (entry.value != baseline._payload[entry.key]) entry.key: entry.value,
    };
    if (changed.isEmpty) throw ApiFailure.invalidInput;
    return Map.unmodifiable(changed);
  }
}

/// Validated changed fields; null is allowed only for the two optional fields.
class AuditPatch {
  AuditPatch._(this.payload);
  factory AuditPatch.fromJson(Object? value) =>
      AuditPatch._(_validate(value, patch: true));
  final Map<String, Object?> payload;
}

/// One immutable create attempt, reused unchanged after an uncertain outcome.
class PendingAuditCreate {
  PendingAuditCreate(AuditDraft draft)
    : key = _uuidV4(),
      payload = Map.unmodifiable(draft.toCreateJson());
  final String key;
  final Map<String, Object?> payload;
  static String _uuidV4() {
    final random = Random.secure();
    final bytes = List<int>.generate(16, (_) => random.nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    final hex = bytes
        .map((byte) => byte.toRadixString(16).padLeft(2, '0'))
        .join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
  }
}
