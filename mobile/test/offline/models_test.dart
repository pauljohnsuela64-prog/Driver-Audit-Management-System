import 'package:flutter_test/flutter_test.dart';
import 'package:bhli_audit/offline/models.dart';

void main() {
  test('preserves established Android Unicode trimming rules exactly', () {
    final values = AuditValues(
      driverName: '\u0085Driver\u0085',
      helperName: '\u0085\u001c',
      auditDate: '2026-11-05',
      station: 'Station',
      plateNumber: '\ufeff00047\ufeff',
      remarks: '\u0085Note\u0085',
    );
    expect(values.driverName, 'Driver');
    expect(values.helperName, isNull);
    expect(values.plateNumber, '\ufeff00047\ufeff');
    expect(values.remarks, 'Note');
  });
  test('normalizes six values and rejects impossible calendar dates', () {
    final values = AuditValues(
      driverName: ' Ada ',
      helperName: ' ',
      auditDate: '2026-11-05',
      station: ' North ',
      plateNumber: ' ABC ',
      remarks: ' note ',
    );
    expect(values.toJson(), {
      'driver_name': 'Ada',
      'helper_name': null,
      'audit_date': '2026-11-05',
      'station': 'North',
      'plate_number': 'ABC',
      'remarks': 'note',
    });
    expect(
      () => AuditValues(
        driverName: 'Ada',
        auditDate: '2026-02-30',
        station: 'N',
        plateNumber: 'A',
      ),
      throwsA(
        isA<OfflineFailure>().having((e) => e.code, 'code', 'validation'),
      ),
    );
    expect(AuditValues.fromJson(values.toJson()).toJson(), values.toJson());
  });
  test('creates distinct RFC4122 version four UUIDs', () {
    final ids = List.generate(100, (_) => newUuid());
    expect(ids.toSet().length, 100);
    for (final id in ids) {
      expect(
        id,
        matches(
          RegExp(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
          ),
        ),
      );
    }
  });
  test('enforces calendar year and text limits after normalization', () {
    AuditValues make({
      String driver = 'D',
      String date = '1000-01-01',
      String? remarks,
    }) => AuditValues(
      driverName: driver,
      auditDate: date,
      station: 'S',
      plateNumber: 'P',
      remarks: remarks,
    );
    expect(make(date: '9999-12-31').auditDate, '9999-12-31');
    expect(make(driver: '😀' * 200).driverName.runes.length, 200);
    for (final date in [
      '0999-12-31',
      '10000-01-01',
      '2025-02-29',
      '2026-13-01',
      '2026-00-01',
    ]) {
      expect(() => make(date: date), throwsA(isA<OfflineFailure>()));
    }
    expect(() => make(driver: ' '), throwsA(isA<OfflineFailure>()));
    expect(() => make(driver: 'D' * 201), throwsA(isA<OfflineFailure>()));
    expect(() => make(remarks: 'R' * 10001), throwsA(isA<OfflineFailure>()));
  });
  test('rejects unexpected fields instead of silently dropping them', () {
    expect(
      () => AuditValues.fromJson({
        'driver_name': 'D',
        'helper_name': null,
        'audit_date': '2026-11-05',
        'station': 'S',
        'plate_number': 'P',
        'remarks': null,
        'audited_by_name': 'Injected',
      }),
      throwsA(isA<OfflineFailure>()),
    );
  });
  test(
    'optional whitespace normalization includes Python control separators',
    () {
      final values = AuditValues(
        driverName: 'D',
        helperName: '\u001c\u001d',
        auditDate: '2026-11-05',
        station: 'S',
        plateNumber: 'P',
        remarks: '\u001e note \u001f',
      );
      expect(values.helperName, isNull);
      expect(values.remarks, 'note');
    },
  );
}
