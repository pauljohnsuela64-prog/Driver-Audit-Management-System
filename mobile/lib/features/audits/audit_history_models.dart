import '../../core/network/api_failure.dart';
import '../../core/network/json_contract.dart';
import 'models.dart';

/// A deliberately restricted projection: arbitrary snapshot metadata never
/// becomes displayable history data.
class AuditSnapshot {
  AuditSnapshot._(AuditRecord record)
    : fields = Map.unmodifiable({
        'driver_name': record.driverName,
        'helper_name': record.helperName,
        'audit_date': record.auditDate,
        'station': record.station,
        'plate_number': record.plateNumber,
        'remarks': record.remarks,
        'audited_by_name': record.auditedByName,
      }),
      archived = record.deletedAt != null;
  final Map<String, String?> fields;
  final bool archived;
}

class AuditHistoryEvent {
  const AuditHistoryEvent._(
    this.id,
    this.auditId,
    this.actorUserId,
    this.action,
    this.before,
    this.after,
    this.createdAt,
  );
  final int id, auditId, actorUserId;
  final String action;
  final AuditSnapshot? before;
  final AuditSnapshot after;
  final DateTime createdAt;
  static AuditHistoryEvent _parse(
    Object? value,
    int auditId,
    AuditAccess access,
  ) {
    final json = jsonObject(value);
    final action = json['action'];
    if (!{'CREATE', 'UPDATE', 'DELETE'}.contains(action) ||
        json['audit_id'] != auditId ||
        !json.containsKey('before_data')) {
      throw ApiFailure.protocol;
    }
    final after = AuditRecord.fromJson(json['after_data'], access: access);
    final before = json['before_data'] == null
        ? null
        : AuditRecord.fromJson(json['before_data'], access: access);
    if (after.id != auditId ||
        (before != null && before.id != auditId) ||
        (action == 'CREATE' && (before != null || after.deletedAt != null)) ||
        (action != 'CREATE' && before == null) ||
        (action == 'UPDATE' && after.deletedAt != null) ||
        (action == 'DELETE' && after.deletedAt == null)) {
      throw ApiFailure.protocol;
    }
    if (before != null &&
        (before.deletedAt != null ||
            after.version != before.version + 1 ||
            before.auditedByUserId != after.auditedByUserId ||
            before.auditedByName != after.auditedByName)) {
      throw ApiFailure.protocol;
    }
    return AuditHistoryEvent._(
      positiveInt(json['id']),
      positiveInt(json['audit_id']),
      positiveInt(json['actor_user_id']),
      action as String,
      before == null ? null : AuditSnapshot._(before),
      AuditSnapshot._(after),
      utcTimestamp(json['created_at']),
    );
  }
}

class AuditHistoryPage {
  AuditHistoryPage._(List<AuditHistoryEvent> items, this.total, this.page)
    : items = List.unmodifiable(items);
  static const pageSize = 10;
  final List<AuditHistoryEvent> items;
  final int total, page;
  int get totalPages => total == 0 ? 1 : (total + pageSize - 1) ~/ pageSize;
  static AuditHistoryPage fromJson(
    Object? value, {
    required int auditId,
    int page = 1,
    AuditAccess access = AuditAccess.active,
  }) {
    if (auditId < 1 || page < 1 || page > 10000) throw ApiFailure.invalidInput;
    final json = jsonObject(value);
    final items = json['items'];
    final total = json['total'];
    if (json['page'] is! int ||
        json['page'] != page ||
        json['page_size'] is! int ||
        json['page_size'] != pageSize ||
        total is! int ||
        total < 0 ||
        items is! List ||
        items.length > pageSize ||
        items.length > total) {
      throw ApiFailure.protocol;
    }
    final events = items
        .map((e) => AuditHistoryEvent._parse(e, auditId, access))
        .toList();
    for (var i = 1; i < events.length; i++) {
      if (events[i].id <= events[i - 1].id) throw ApiFailure.protocol;
    }
    return AuditHistoryPage._(events, total, page);
  }
}
