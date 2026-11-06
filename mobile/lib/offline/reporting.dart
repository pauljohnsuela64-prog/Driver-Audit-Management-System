import 'dart:convert';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:sqflite/sqflite.dart';

import 'models.dart';

const reportMaxRows = 20000;
const reportMaxBytes = 100 * 1024 * 1024;
const reportMaxDuration = Duration(minutes: 10);

abstract interface class OfflineReportingRepository {
  Future<OfflineReportSnapshot> reportSnapshot(
    AuditFilter filter, {
    bool includeRows = false,
    bool Function()? cancel,
  });
}

class ReportStation {
  const ReportStation(this.name, this.count, {this.other = false});
  final String name;
  final int count;
  final bool other;
}

class OfflineReportSnapshot {
  OfflineReportSnapshot({
    required this.filter,
    required this.snapshotUtc,
    required this.total,
    required this.active,
    required this.archived,
    required this.displayed,
    required List<ReportStation> stations,
    required List<LocalAudit> rows,
    required this.hasRows,
  }) : stations = List.unmodifiable(stations),
       rows = List.unmodifiable(rows);
  final AuditFilter filter;
  final DateTime snapshotUtc;
  final int total, active, archived, displayed;
  final List<ReportStation> stations;
  final List<LocalAudit> rows;
  final bool hasRows;
}

Never _limit() => throw const OfflineFailure(
  'report_limit',
  'The report exceeds safe limits. Narrow the applied filters and try again.',
);
void _check(Stopwatch clock, bool Function()? cancel) {
  if (cancel?.call() ?? false) {
    throw const OfflineFailure('cancelled', 'Report cancelled.');
  }
  if (clock.elapsed > reportMaxDuration) _limit();
}

List<String?> reportFields(LocalAudit a) => [
  a.values.driverName,
  a.values.helperName,
  a.values.auditDate,
  a.values.station,
  a.values.plateNumber,
  a.values.remarks,
  a.auditedByName,
];

/// This helper runs entirely inside the repository's queued read transaction.
Future<OfflineReportSnapshot> reportSnapshotTransaction(
  DatabaseExecutor txn,
  AuditFilter filter, {
  bool includeRows = false,
  bool Function()? cancel,
}) async {
  final clock = Stopwatch()..start();
  _check(clock, cancel);
  if (!{
        'created',
        '-created',
        'audit_date',
        '-audit_date',
      }.contains(filter.sort) ||
      (filter.dateFrom != null && !validOfflineDate(filter.dateFrom!)) ||
      (filter.dateTo != null && !validOfflineDate(filter.dateTo!)) ||
      (filter.dateFrom != null &&
          filter.dateTo != null &&
          filter.dateFrom!.compareTo(filter.dateTo!) > 0)) {
    invalidInput();
  }
  final clauses = <String>[];
  final args = <Object?>[];
  for (final e in {
    'driver_name': filter.driver,
    'plate_number': filter.plate,
    'station': filter.station,
  }.entries) {
    final value = offlineText(e.value, 200, optional: true);
    if (value.isNotEmpty) {
      clauses.add("${e.key} LIKE ? ESCAPE '\\'");
      args.add(
        '%${value.replaceAll('\\', '\\\\').replaceAll('%', '\\%').replaceAll('_', '\\_')}%',
      );
    }
  }
  if (filter.dateFrom != null) {
    clauses.add('audit_date >= ?');
    args.add(filter.dateFrom);
  }
  if (filter.dateTo != null) {
    clauses.add('audit_date <= ?');
    args.add(filter.dateTo);
  }
  final base = clauses.isEmpty ? '1' : clauses.join(' AND ');
  final scope =
      '$base${filter.includeArchived ? '' : ' AND archived_at IS NULL'}';
  final counts = (await txn.rawQuery(
    'SELECT COUNT(*) AS total, COALESCE(SUM(archived_at IS NULL),0) AS active, COALESCE(SUM(archived_at IS NOT NULL),0) AS archived FROM audit_records WHERE $base',
    args,
  )).single;
  final total = counts['total'] as int,
      active = counts['active'] as int,
      archived = counts['archived'] as int;
  final displayed = filter.includeArchived ? total : active;
  final snapshotUtc = DateTime.now().toUtc();
  final grouped = await txn.rawQuery(
    'SELECT station, COUNT(*) AS n FROM audit_records WHERE $scope GROUP BY station ORDER BY n DESC, station COLLATE BINARY ASC LIMIT 10',
    args,
  );
  final stations = <ReportStation>[];
  var other = displayed;
  for (final group in grouped) {
    final count = group['n'] as int;
    stations.add(ReportStation(group['station'] as String, count));
    other -= count;
  }
  if (other > 0) {
    stations.add(ReportStation('Other stations', other, other: true));
  }
  final rows = <LocalAudit>[];
  if (includeRows) {
    if (displayed > reportMaxRows) _limit();
    final order = switch (filter.sort) {
      'created' => 'seq ASC',
      '-created' => 'seq DESC',
      'audit_date' => 'audit_date ASC, seq ASC',
      _ => 'audit_date DESC, seq DESC',
    };
    // Bounded batches within this SAME transaction, never public paged reads.
    var bytes = 0;
    for (var offset = 0; offset < displayed; offset += 100) {
      _check(clock, cancel);
      final batch = await txn.query(
        'audit_records',
        where: scope,
        whereArgs: args,
        orderBy: order,
        limit: 100,
        offset: offset,
      );
      for (final r in batch) {
        final a = LocalAudit(
          id: r['id'] as String,
          values: AuditValues(
            driverName: r['driver_name'] as String,
            helperName: r['helper_name'] as String?,
            auditDate: r['audit_date'] as String,
            station: r['station'] as String,
            plateNumber: r['plate_number'] as String,
            remarks: r['remarks'] as String?,
          ),
          auditedByName: r['audited_by_name'] as String,
          profileId: r['profile_id'] as String,
          createdAt: DateTime.parse(r['created_at'] as String),
          updatedAt: DateTime.parse(r['updated_at'] as String),
          revision: r['revision'] as int,
          archivedAt: r['archived_at'] == null
              ? null
              : DateTime.parse(r['archived_at'] as String),
        );
        for (final field in [a.id, ...reportFields(a)]) {
          bytes += utf8.encode(field ?? '').length;
          if (bytes > reportMaxBytes) _limit();
        }
        rows.add(a);
      }
    }
    if (rows.length != displayed) {
      throw const OfflineFailure(
        'report_snapshot',
        'The report snapshot could not be completed.',
      );
    }
  }
  _check(clock, cancel);
  return OfflineReportSnapshot(
    filter: filter,
    snapshotUtc: snapshotUtc,
    total: total,
    active: active,
    archived: archived,
    displayed: displayed,
    stations: stations,
    rows: rows,
    hasRows: includeRows,
  );
}

String safeReportText(String value) {
  final out = StringBuffer();
  for (final rune in value.runes) {
    if (rune == 10) {
      out.write('\n');
    } else if (rune < 32 ||
        (rune >= 127 && rune <= 159) ||
        (rune >= 0x2028 && rune <= 0x202e) ||
        (rune >= 0x2066 && rune <= 0x2069)) {
      out.write('\\u${rune.toRadixString(16).padLeft(4, '0')}');
    } else {
      out.writeCharCode(rune);
    }
  }
  return out.toString();
}

String _inlineReportText(String value) =>
    safeReportText(value).replaceAll('\n', r'\u000a');
String reportFilterDescription(AuditFilter f) =>
    'Driver: ${_inlineReportText(f.driver.isEmpty ? 'All' : f.driver)}; Plate: ${_inlineReportText(f.plate.isEmpty ? 'All' : f.plate)}; Station: ${_inlineReportText(f.station.isEmpty ? 'All' : f.station)}\nDate range: ${f.dateFrom ?? 'Any'} to ${f.dateTo ?? 'Any'} (inclusive)\nInclude archived: ${f.includeArchived ? 'Yes' : 'No'}; Order: ${f.sort}';
Future<Uint8List> encodeTextReport(OfflineReportSnapshot snapshot) =>
    Isolate.run(() => _encode(snapshot));
Uint8List _encode(OfflineReportSnapshot s) {
  if (!s.hasRows ||
      s.rows.length != s.displayed ||
      s.rows.length > reportMaxRows) {
    _limit();
  }
  final clock = Stopwatch()..start();
  final out = BytesBuilder(copy: false);
  void add(String text) {
    _check(clock, null);
    final bytes = utf8.encode(text);
    if (out.length + bytes.length > reportMaxBytes) _limit();
    out.add(bytes);
  }

  void field(String label, String? text) {
    add(
      '$label:\n  ${safeReportText(text ?? 'Not provided').replaceAll('\n', '\n  ')}\n',
    );
  }

  add(
    'BHLI Audit Offline - readable text report\nOffline development edition - fictional data only\nUnencrypted report: protect this file.\nPoint-in-time local snapshot\nGenerated UTC: ${DateTime.now().toUtc().toIso8601String()}\nSnapshot UTC: ${s.snapshotUtc.toIso8601String()}\nApplied filters:\n${reportFilterDescription(s.filter)}\nAll-status matching total: ${s.total}\nActive: ${s.active}\nArchived: ${s.archived}\nDisplayed scope: ${s.displayed}\nInclude archived changes the displayed result set. Active + archived equals all-status total.\nStations (displayed scope):\n',
  );
  for (final station in s.stations) {
    field(
      station.other ? 'Other stations' : 'Station',
      '${station.name}: ${station.count}',
    );
  }
  if (s.rows.isEmpty) add('\nZero matching audits.\n');
  for (final a in s.rows) {
    add('\n----------------------------------------\n');
    field('Record ID', a.id);
    field('Status', a.archived ? 'Archived' : 'Active');
    final fields = reportFields(a);
    const labels = [
      'Driver Name',
      'Helper Name',
      'Audit Date',
      'Station',
      'Plate Number',
      'Remarks',
      'Audited By',
    ];
    for (var i = 0; i < labels.length; i++) {
      field(labels[i], fields[i]);
    }
  }
  return out.takeBytes();
}
