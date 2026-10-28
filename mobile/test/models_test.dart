import 'package:flutter_test/flutter_test.dart';
import 'package:bhli_audit/core/network/api_failure.dart';
import 'package:bhli_audit/features/auth/models.dart';
import 'package:bhli_audit/features/audits/models.dart';

import 'network_test_support.dart';

void main() {
  test(
    'calendar dates validate Gregorian dates without timezone conversion',
    () {
      expect(CalendarDate.parse('2024-02-29').value, '2024-02-29');
      for (final value in [
        '0999-12-31',
        '2023-02-29',
        '2024-04-31',
        '2024-2-01',
        '2024-01-01T00:00:00Z',
        '2024-13-01',
      ]) {
        expect(() => CalendarDate.parse(value), throwsA(isA<ApiFailure>()));
      }
    },
  );

  test('record preserves seven business fields, historical attribution and metadata', () {
    final record = AuditRecord.fromJson(auditJson());
    expect(record.driverName, 'José 🚚');
    expect(record.helperName, isNull);
    expect(record.auditDate, '2024-02-29');
    expect(record.plateNumber, '000123');
    expect(record.remarks, '<b>plain text</b>\nSecond line');
    expect(record.auditedByName, 'Original Snapshot');
    expect(record.auditedByUserId, 8);
    expect(record.version, 3);
    expect(record.updatedAt, DateTime.utc(2026, 10, 28, 8, 30));
  });

  test('record rejects absent, wrong-type, impossible and archived values', () {
    for (final change in <String, Object?>{
      'id': 0,
      'version': 1.5,
      'driver_name': 45,
      'plate_number': null,
      'audit_date': '2023-02-29',
      'created_at': '2026-10-28T08:00:00',
      'updated_by_user_id': -1,
      'deleted_at': '2026-10-28T08:00:00Z',
    }.entries) {
      expect(
        () => AuditRecord.fromJson({...auditJson(), change.key: change.value}),
        throwsA(isA<ApiFailure>()),
        reason: change.key,
      );
    }
    final missing = auditJson()..remove('helper_name');
    expect(() => AuditRecord.fromJson(missing), throwsA(isA<ApiFailure>()));
  });

  test(
    'query emits exact backend parameters and keeps Unicode code point bounds',
    () {
      final query = AuditQuery(
        driverName: '  José 🚚  ',
        plateNumber: '0001',
        station: 'A&B',
        dateFrom: '2024-02-29',
        dateTo: '2024-03-01',
        sort: 'audit_date',
        page: 2,
      );
      expect(query.toQueryParameters(), {
        'driver_name': 'José 🚚',
        'plate_number': '0001',
        'station': 'A&B',
        'date_from': '2024-02-29',
        'date_to': '2024-03-01',
        'sort': 'audit_date',
        'page': '2',
        'page_size': '25',
      });
      expect(AuditQuery(driverName: '🚚' * 200).driverName!.runes.length, 200);
      expect(
        AuditQuery(station: '   ').toQueryParameters().containsKey('station'),
        false,
      );
      expect(
        () => AuditQuery(driverName: '🚚' * 201),
        throwsA(isA<ApiFailure>()),
      );
      expect(() => AuditQuery(page: 10001), throwsA(isA<ApiFailure>()));
      expect(() => AuditQuery(sort: 'created_at'), throwsA(isA<ApiFailure>()));
      expect(
        () => AuditQuery(dateFrom: '2024-03-01', dateTo: '2024-02-29'),
        throwsA(isA<ApiFailure>()),
      );
      expect(query.copyWith(page: 3).toQueryParameters()['page'], '3');
    },
  );

  test('page rejects mismatched echo and unbounded or inconsistent items', () {
    final query = AuditQuery(page: 2);
    final json = {
      'items': [auditJson()],
      'total': 26,
      'page': 2,
      'page_size': 25,
    };
    final page = AuditPage.fromJson(json, query);
    expect(page.totalPages, 2);
    expect(() => page.items.clear(), throwsUnsupportedError);
    for (final change in <String, Object?>{
      'page': 1,
      'page_size': 100,
      'total': -1,
      'items': List.generate(26, (i) => auditJson(id: i + 1)),
    }.entries) {
      expect(
        () => AuditPage.fromJson({...json, change.key: change.value}, query),
        throwsA(isA<ApiFailure>()),
      );
    }
  });

  test('lease validates opaque bearer and requires an explicit UTC offset', () {
    expect(SessionLease.fromJson(leaseJson()).expiresAt.isUtc, true);
    for (final token in ['jwt.a.b', 'A' * 42, '${'A' * 42}=', '$tokenA\n']) {
      expect(
        () => SessionLease.fromJson(leaseJson(token: token)),
        throwsA(isA<ApiFailure>()),
      );
    }
    expect(
      () => SessionLease.fromJson({...leaseJson(), 'token_type': 'JWT'}),
      throwsA(isA<ApiFailure>()),
    );
    expect(
      () => SessionLease.fromJson({
        ...leaseJson(),
        'expires_at': '2026-10-28T20:00:00',
      }),
      throwsA(isA<ApiFailure>()),
    );
    expect(
      SessionLease.fromJson(leaseJson()).toString(),
      isNot(contains(tokenA)),
    );
  });

  test('unknown roles fail closed and user identity fields are strict', () {
    expect(AuthenticatedUser.fromJson(userJson(role: 'ADMIN')).role, 'ADMIN');
    expect(
      () => AuthenticatedUser.fromJson(userJson(role: 'VIEWER')),
      throwsA(isA<ApiFailure>()),
    );
    expect(
      () => AuthenticatedUser.fromJson({...userJson(), 'id': true}),
      throwsA(isA<ApiFailure>()),
    );
  });
}
