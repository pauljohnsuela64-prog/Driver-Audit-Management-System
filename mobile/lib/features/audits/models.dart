import '../../core/network/api_failure.dart';
import '../../core/network/json_contract.dart';

class CalendarDate {
  const CalendarDate._(this.value);
  final String value;
  static CalendarDate parse(String value) {
    if (!validCalendarDate(value)) throw ApiFailure.invalidInput;
    return CalendarDate._(value);
  }

  @override
  String toString() => value;
}

class AuditRecord {
  const AuditRecord._({
    required this.id,
    required this.version,
    required this.driverName,
    required this.helperName,
    required this.auditDate,
    required this.station,
    required this.plateNumber,
    required this.remarks,
    required this.auditedByName,
    required this.auditedByUserId,
    required this.updatedByUserId,
    required this.deletedByUserId,
    required this.deletedAt,
    required this.createdAt,
    required this.updatedAt,
    this.etag,
  });
  final int id;
  final int version;
  final String driverName;
  final String? helperName;
  final String auditDate;
  final String station;
  final String plateNumber;
  final String? remarks;
  final String auditedByName;
  final int auditedByUserId;
  final int? updatedByUserId;
  final int? deletedByUserId;
  final DateTime? deletedAt;
  final DateTime createdAt;
  final DateTime updatedAt;
  final String? etag;

  static AuditRecord fromJson(Object? value, {String? etag}) {
    final json = jsonObject(value);
    final version = positiveInt(json['version']);
    final date = json['audit_date'];
    if (date is! String ||
        !validCalendarDate(date) ||
        !json.containsKey('deleted_at') ||
        json['deleted_at'] != null ||
        (etag != null && etag != '"$version"')) {
      throw ApiFailure.protocol;
    }
    final deletedBy = nullablePositiveInt(json, 'deleted_by_user_id');
    if (deletedBy != null) throw ApiFailure.protocol;
    return AuditRecord._(
      id: positiveInt(json['id']),
      version: version,
      driverName: requiredText(json['driver_name'], maxLength: 200),
      helperName: nullableText(json, 'helper_name', maxLength: 200),
      auditDate: date,
      station: requiredText(json['station'], maxLength: 150),
      plateNumber: requiredText(json['plate_number'], maxLength: 30),
      remarks: nullableText(json, 'remarks', maxLength: 10000),
      auditedByName: requiredText(json['audited_by_name'], maxLength: 200),
      auditedByUserId: positiveInt(json['audited_by_user_id']),
      updatedByUserId: nullablePositiveInt(json, 'updated_by_user_id'),
      deletedByUserId: deletedBy,
      deletedAt: null,
      createdAt: utcTimestamp(json['created_at']),
      updatedAt: utcTimestamp(json['updated_at']),
      etag: etag,
    );
  }
}

class AuditQuery {
  const AuditQuery._({
    this.driverName,
    this.plateNumber,
    this.station,
    this.dateFrom,
    this.dateTo,
    required this.sort,
    required this.page,
  });
  factory AuditQuery({
    String? driverName,
    String? plateNumber,
    String? station,
    String? dateFrom,
    String? dateTo,
    String sort = '-id',
    int page = 1,
  }) {
    if (page < 1 ||
        page > 10000 ||
        !{'id', '-id', 'audit_date', '-audit_date'}.contains(sort)) {
      throw ApiFailure.invalidInput;
    }
    if (dateFrom != null) CalendarDate.parse(dateFrom);
    if (dateTo != null) CalendarDate.parse(dateTo);
    if (dateFrom != null && dateTo != null && dateFrom.compareTo(dateTo) > 0) {
      throw ApiFailure.invalidInput;
    }
    return AuditQuery._(
      driverName: _search(driverName),
      plateNumber: _search(plateNumber),
      station: _search(station),
      dateFrom: dateFrom,
      dateTo: dateTo,
      sort: sort,
      page: page,
    );
  }
  final String? driverName;
  final String? plateNumber;
  final String? station;
  final String? dateFrom;
  final String? dateTo;
  final String sort;
  final int page;
  int get pageSize => 25;
  static String? _search(String? value) {
    final trimmed = value?.trim();
    if (trimmed == null || trimmed.isEmpty) return null;
    if (trimmed.runes.length > 200) throw ApiFailure.invalidInput;
    return trimmed;
  }

  AuditQuery copyWith({int? page}) => AuditQuery(
    driverName: driverName,
    plateNumber: plateNumber,
    station: station,
    dateFrom: dateFrom,
    dateTo: dateTo,
    sort: sort,
    page: page ?? this.page,
  );
  Map<String, String> toQueryParameters() => {
    'driver_name': ?driverName,
    'plate_number': ?plateNumber,
    'station': ?station,
    'date_from': ?dateFrom,
    'date_to': ?dateTo,
    'sort': sort,
    'page': '$page',
    'page_size': '$pageSize',
  };
}

class AuditPage {
  AuditPage._(List<AuditRecord> items, this.total, this.page, this.pageSize)
    : items = List.unmodifiable(items);
  final List<AuditRecord> items;
  final int total;
  final int page;
  final int pageSize;
  int get totalPages => total == 0 ? 1 : (total + pageSize - 1) ~/ pageSize;
  static AuditPage fromJson(Object? value, AuditQuery query) {
    final json = jsonObject(value);
    final total = json['total'];
    final page = json['page'];
    final pageSize = json['page_size'];
    final items = json['items'];
    if (total is! int ||
        total < 0 ||
        page is! int ||
        page != query.page ||
        pageSize is! int ||
        pageSize != query.pageSize ||
        items is! List ||
        items.length > query.pageSize) {
      throw ApiFailure.protocol;
    }
    return AuditPage._(
      items.map(AuditRecord.fromJson).toList(),
      total,
      page,
      pageSize,
    );
  }
}
