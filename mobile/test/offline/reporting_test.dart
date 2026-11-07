import 'dart:io';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/sqlite_repository.dart';
import 'package:bhli_audit/offline/reporting.dart';

void main() {
  setUpAll(sqfliteFfiInit);
  late Directory dir;
  late SqliteOfflineRepository repo;
  setUp(() async {
    dir = await Directory.systemTemp.createTemp('fictional-report-');
    repo = await SqliteOfflineRepository.open(
      '${dir.path}/test.db',
      factory: databaseFactoryFfi,
    );
    await repo.saveProfile('Original Auditor');
  });
  tearDown(() async {
    await repo.close();
    await dir.delete(recursive: true);
  });
  test('report includes all pages, reconciles status/stations and preserves literal seven fields', () async {
    for (var i = 0; i < 27; i++) {
      final a = await repo.create(
        newUuid(),
        AuditValues(
          driverName: 'Driver $i',
          auditDate: '2026-11-06',
          station: 'Station ${i % 12}',
          plateNumber: '00123',
          remarks: '\u65e5\u672c\u8a9e\u{1f69a}\nStatus: forged\u0001',
        ),
      );
      if (i == 0) await repo.archive(a.id, a.revision);
    }
    await repo.saveProfile('Changed Auditor');
    final report = await repo.reportSnapshot(
      const AuditFilter(page: 2, pageSize: 1),
      includeRows: true,
    );
    expect(report.total, 27);
    expect(report.active, 26);
    expect(report.archived, 1);
    expect(report.displayed, 26);
    expect(report.rows.length, 26);
    expect(report.stations.length, 11);
    expect(report.stations.last.other, true);
    expect(report.stations.fold<int>(0, (n, s) => n + s.count), 26);
    final text = utf8.decode(await encodeTextReport(report));
    expect(text, contains('Plate Number:\n  00123'));
    expect(
      text,
      contains(
        'Remarks:\n  \u65e5\u672c\u8a9e\u{1f69a}\n  Status: forged\\u0001',
      ),
    );
    expect(text, contains('Audited By:\n  Original Auditor'));
    expect(text, contains('Helper Name:\n  Not provided'));
    expect(text, contains('Driver Name:\n  Driver'));
    expect(text, contains('Audit Date:\n  2026-11-06'));
    expect(text, contains('Station:\n  Station'));
    expect(text, contains('Record ID:\n  ${report.rows.first.id}'));
    expect(text, contains('Status:\n  Active'));
    expect(text, contains('Point-in-time local snapshot'));
    expect(text, contains('Unencrypted report'));
    final all = await repo.reportSnapshot(
      const AuditFilter(includeArchived: true),
      includeRows: true,
    );
    expect(all.displayed, 27);
    expect(all.rows.where((a) => a.archived).length, 1);
    expect(all.stations.fold<int>(0, (n, s) => n + s.count), 27);
  });
  test('applied literal searches, inclusive dates and stable order ignore pagination', () async {
    final ids = <String>[];
    for (final driver in ['Match%_', 'MatchXX', 'Match%_']) {
      final a = await repo.create(
        newUuid(),
        AuditValues(
          driverName: driver,
          helperName: '\u{1f69a}',
          auditDate: '2026-11-06',
          station: 'North',
          plateNumber: '00001',
        ),
      );
      ids.add(a.id);
    }
    final report = await repo.reportSnapshot(
      const AuditFilter(
        driver: '%_',
        plate: '000',
        station: 'orth',
        dateFrom: '2026-11-06',
        dateTo: '2026-11-06',
        sort: 'audit_date',
        page: 99,
        pageSize: 1,
      ),
      includeRows: true,
    );
    expect(report.rows.map((a) => a.id), [ids[0], ids[2]]);
    expect(report.total, 2);
    expect(
      (await repo.reportSnapshot(const AuditFilter(dateFrom: '2026-11-07')))
          .displayed,
      0,
    );
    await expectLater(
      repo.reportSnapshot(
        const AuditFilter(dateFrom: '2026-11-07', dateTo: '2026-11-06'),
      ),
      throwsA(isA<OfflineFailure>()),
    );
  });
  test('zero summary does not pretend rows were captured; empty complete report is labelled', () async {
    final summary = await repo.reportSnapshot(const AuditFilter());
    expect(summary.rows, isEmpty);
    expect(summary.hasRows, false);
    expect(summary.total, 0);
    expect(summary.stations, isEmpty);
    await expectLater(
      encodeTextReport(summary),
      throwsA(isA<OfflineFailure>()),
    );
    final empty = await repo.reportSnapshot(
      const AuditFilter(),
      includeRows: true,
    );
    expect(
      utf8.decode(await encodeTextReport(empty)),
      contains('Zero matching audits.'),
    );
    await expectLater(
      repo.reportSnapshot(const AuditFilter(), cancel: () => true),
      throwsA(isA<OfflineFailure>().having((e) => e.code, 'code', 'cancelled')),
    );
  });
  test('read snapshot survives concurrent WAL writer with consistent original rows', () async {
    final a = await repo.create(
      newUuid(),
      AuditValues(
        driverName: 'Before',
        auditDate: '2026-11-06',
        station: 'North',
        plateNumber: '001',
      ),
    );
    final reader = await databaseFactoryFfi.openDatabase(
      '${dir.path}/test.db',
      options: OpenDatabaseOptions(singleInstance: false),
    );
    final writer = await databaseFactoryFfi.openDatabase(
      '${dir.path}/test.db',
      options: OpenDatabaseOptions(singleInstance: false),
    );
    try {
      await reader.rawQuery('PRAGMA journal_mode=WAL');
      await reader.execute('BEGIN DEFERRED');
      try {
        await reader.rawQuery('SELECT COUNT(*) FROM audit_records');
        await writer.update(
          'audit_records',
          {'driver_name': 'After'},
          where: 'id = ?',
          whereArgs: [a.id],
        );
        final report = await reportSnapshotTransaction(
          reader,
          const AuditFilter(),
          includeRows: true,
        );
        expect(report.displayed, 1);
        expect(report.rows.single.values.driverName, 'Before');
      } finally {
        await reader.execute('ROLLBACK');
      }
      expect(
        (await repo.reportSnapshot(
          const AuditFilter(),
          includeRows: true,
        )).rows.single.values.driverName,
        'After',
      );
    } finally {
      await writer.close();
      await reader.close();
    }
  });
  test('summary remains bounded to counts when full report row ceiling is exceeded', () async {
    await repo.create(
      newUuid(),
      AuditValues(
        driverName: 'Fictional',
        auditDate: '2026-11-06',
        station: 'North',
        plateNumber: '000',
      ),
    );
    final db = await databaseFactoryFfi.openDatabase(
      '${dir.path}/test.db',
      options: OpenDatabaseOptions(singleInstance: false),
    );
    try {
      await db.execute(
        "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<20000) INSERT INTO audit_records (id,driver_name,helper_name,audit_date,station,plate_number,remarks,audited_by_name,profile_id,created_at,updated_at,revision,archived_at) SELECT printf('%08x-0000-4000-8000-000000000000',n.x),a.driver_name,a.helper_name,a.audit_date,a.station,a.plate_number,a.remarks,a.audited_by_name,a.profile_id,a.created_at,a.updated_at,a.revision,a.archived_at FROM n CROSS JOIN (SELECT * FROM audit_records LIMIT 1) AS a",
      );
      expect((await repo.reportSnapshot(const AuditFilter())).displayed, 20001);
      await expectLater(
        repo.reportSnapshot(const AuditFilter(), includeRows: true),
        throwsA(
          isA<OfflineFailure>().having((e) => e.code, 'code', 'report_limit'),
        ),
      );
    } finally {
      await db.close();
    }
  });
  test('filter metadata cannot forge another report heading', () {
    final description = reportFilterDescription(
      const AuditFilter(driver: 'query\nStatus: forged'),
    );
    expect(description, contains(r'query\u000aStatus: forged'));
  });
  test('text output refuses row and UTF8 byte ceilings without returning partial output', () async {
    final a = LocalAudit(
      id: newUuid(),
      values: AuditValues(
        driverName: 'Driver',
        auditDate: '2026-11-06',
        station: 'North',
        plateNumber: '000',
        remarks: List.filled(10000, '\u{1f69a}').join(),
      ),
      auditedByName: 'Original',
      profileId: newUuid(),
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      revision: 1,
    );
    OfflineReportSnapshot snapshot(int count) => OfflineReportSnapshot(
      filter: const AuditFilter(),
      snapshotUtc: DateTime.utc(2026),
      total: count,
      active: count,
      archived: 0,
      displayed: count,
      stations: [],
      rows: List.filled(count, a),
      hasRows: true,
    );
    await expectLater(
      encodeTextReport(snapshot(20001)),
      throwsA(isA<OfflineFailure>()),
    );
    await expectLater(
      encodeTextReport(snapshot(2700)),
      throwsA(isA<OfflineFailure>()),
    );
    expect(
      safeReportText('x\r\t\u001b\u0085\u2028\u2029\u202ey'),
      'x\\u000d\\u0009\\u001b\\u0085\\u2028\\u2029\\u202ey',
    );
  });
}
