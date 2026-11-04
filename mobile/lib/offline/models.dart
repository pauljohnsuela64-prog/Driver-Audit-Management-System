import 'dart:math';

class OfflineFailure implements Exception {
  const OfflineFailure(this.code, this.message);
  final String code;
  final String message;
  @override
  String toString() => message;
}

Never invalidInput() =>
    throw const OfflineFailure('validation', 'Check the entered values.');

bool validOfflineDate(String value) {
  if (!RegExp(r'^[1-9][0-9]{3}-[0-9]{2}-[0-9]{2}$').hasMatch(value)) {
    return false;
  }
  final year = int.parse(value.substring(0, 4));
  final month = int.parse(value.substring(5, 7));
  final day = int.parse(value.substring(8, 10));
  final date = DateTime.utc(year, month, day);
  return date.year == year && date.month == month && date.day == day;
}

String offlineText(String value, int limit, {bool optional = false}) {
  final text = optional
      ? value.replaceAll(RegExp(r'^[\s\u001c-\u001f]+|[\s\u001c-\u001f]+$'), '')
      : value.trim();
  if ((!optional && text.isEmpty) || text.runes.length > limit) invalidInput();
  return text;
}

bool validOfflineUuid(String id) => RegExp(
  r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
).hasMatch(id);

String newUuid() {
  final random = Random.secure();
  final bytes = List.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  final hex = bytes
      .map((byte) => byte.toRadixString(16).padLeft(2, '0'))
      .join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
}

class AuditValues {
  AuditValues({
    required String driverName,
    String? helperName,
    required String auditDate,
    required String station,
    required String plateNumber,
    String? remarks,
  }) : driverName = offlineText(driverName, 200),
       helperName = _optional(helperName, 200),
       auditDate = auditDate,
       station = offlineText(station, 150),
       plateNumber = offlineText(plateNumber, 30),
       remarks = _optional(remarks, 10000) {
    if (!validOfflineDate(auditDate)) invalidInput();
  }
  final String driverName;
  final String? helperName;
  final String auditDate;
  final String station;
  final String plateNumber;
  final String? remarks;
  static String? _optional(String? value, int limit) {
    if (value == null) return null;
    final text = offlineText(value, limit, optional: true);
    return text.isEmpty ? null : text;
  }

  Map<String, Object?> toJson() => {
    'driver_name': driverName,
    'helper_name': helperName,
    'audit_date': auditDate,
    'station': station,
    'plate_number': plateNumber,
    'remarks': remarks,
  };
  factory AuditValues.fromJson(Map<String, Object?> json) {
    if (json.keys.toSet().difference({
      'driver_name',
      'helper_name',
      'audit_date',
      'station',
      'plate_number',
      'remarks',
    }).isNotEmpty) {
      invalidInput();
    }
    if (json['driver_name'] is! String ||
        json['audit_date'] is! String ||
        json['station'] is! String ||
        json['plate_number'] is! String ||
        (json['helper_name'] != null && json['helper_name'] is! String) ||
        (json['remarks'] != null && json['remarks'] is! String)) {
      invalidInput();
    }
    return AuditValues(
      driverName: json['driver_name'] as String,
      helperName: json['helper_name'] as String?,
      auditDate: json['audit_date'] as String,
      station: json['station'] as String,
      plateNumber: json['plate_number'] as String,
      remarks: json['remarks'] as String?,
    );
  }
}

class LocalProfile {
  const LocalProfile({required this.id, required this.name});
  final String id;
  final String name;
}

class LocalAudit {
  const LocalAudit({
    required this.id,
    required this.values,
    required this.auditedByName,
    required this.profileId,
    required this.createdAt,
    required this.updatedAt,
    required this.revision,
    this.archivedAt,
  });
  final String id;
  final AuditValues values;
  final String auditedByName;
  final String profileId;
  final DateTime createdAt;
  final DateTime updatedAt;
  final int revision;
  final DateTime? archivedAt;
  bool get archived => archivedAt != null;
}

class AuditFilter {
  const AuditFilter({
    this.driver = '',
    this.plate = '',
    this.station = '',
    this.dateFrom,
    this.dateTo,
    this.includeArchived = false,
    this.sort = '-created',
    this.page = 1,
    this.pageSize = 25,
  });
  final String driver;
  final String plate;
  final String station;
  final String? dateFrom;
  final String? dateTo;
  final bool includeArchived;
  final String sort;
  final int page;
  final int pageSize;
}

class AuditPage {
  AuditPage({
    required List<LocalAudit> items,
    required this.total,
    required this.page,
    required this.pageSize,
  }) : items = List.unmodifiable(items);
  final List<LocalAudit> items;
  final int total;
  final int page;
  final int pageSize;
}

class LocalEvent {
  LocalEvent({
    required this.id,
    required this.auditId,
    required this.revision,
    required this.action,
    required this.actorName,
    required this.createdAt,
    this.actorProfileId,
    Map<String, Object?>? before,
    Map<String, Object?>? after,
  }) : before = before == null ? null : Map.unmodifiable(before),
       after = after == null ? null : Map.unmodifiable(after);
  final String id;
  final String auditId;
  final int revision;
  final String action;
  final String actorName;
  final String? actorProfileId;
  final DateTime createdAt;
  final Map<String, Object?>? before;
  final Map<String, Object?>? after;
}
