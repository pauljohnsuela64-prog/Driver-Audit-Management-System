import 'package:flutter_test/flutter_test.dart';
import 'package:bhli_audit/core/network/api_failure.dart';
import 'package:bhli_audit/features/audits/audit_draft.dart';

Map<String, Object?> fields() => {
  'driver_name': 'Driver',
  'helper_name': null,
  'audit_date': '2024-02-29',
  'station': 'Station',
  'plate_number': 'ABC',
  'remarks': null,
};
AuditDraft draft(Map<String, Object?> changes) =>
    AuditDraft.fromJson({...fields(), ...changes});
void main() {
  test('patch validates allowlist types nullability and freezes normalized changes', () {
    for (final value in [
      null,
      {},
      {'id': 3},
      {'station': null},
      {'driver_name': 4},
      {'remarks': 4},
    ]) {
      expect(
        () => AuditPatch.fromJson(value),
        throwsA(ApiFailure.invalidInput),
      );
    }
    final source = <String, Object?>{'station': ' New ', 'remarks': '  '};
    final patch = AuditPatch.fromJson(source);
    source['station'] = 'Mutated';
    expect(patch.payload, {'station': 'New', 'remarks': null});
    expect(() => patch.payload['station'] = 'Other', throwsUnsupportedError);
  });
  test('normalizes backend golden whitespace vectors preserving BOM', () {
    for (final boundary in ['\u001c', '\u0085', '\u00a0', '\ufeff']) {
      final result = draft({
        'driver_name': '${boundary}X$boundary',
        'helper_name': '${boundary}X$boundary',
      }).toCreateJson();
      expect(
        result['driver_name'],
        boundary == '\u001c' || boundary == '\ufeff'
            ? '${boundary}X$boundary'
            : 'X',
      );
      expect(
        result['helper_name'],
        boundary == '\ufeff' ? '${boundary}X$boundary' : 'X',
      );
    }
  });
  test('required and optional fields use distinct whitespace sets', () {
    const whitespace =
        '\u0009\u000a\u000b\u000c\u000d\u0020\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000';
    expect(
      draft({
        'driver_name': '${whitespace}X$whitespace',
        'helper_name': '\u001c\u001d\u001e\u001f$whitespace',
      }).toCreateJson(),
      {...fields(), 'driver_name': 'X'},
    );
    expect(
      () => draft({'driver_name': whitespace}),
      throwsA(ApiFailure.invalidInput),
    );
  });
  test('limits count code points for every text field', () {
    for (final entry in {
      'driver_name': 200,
      'helper_name': 200,
      'station': 150,
      'plate_number': 30,
      'remarks': 10000,
    }.entries) {
      expect(
        draft({entry.key: '\u{1f600}' * entry.value}).toCreateJson()[entry.key],
        '\u{1f600}' * entry.value,
      );
      expect(
        () => draft({entry.key: '\u{1f600}' * (entry.value + 1)}),
        throwsA(ApiFailure.invalidInput),
      );
    }
  });
  test('validates real calendar dates within MySQL bounds', () {
    for (final date in ['1000-01-01', '9999-12-31', '2000-02-29']) {
      expect(draft({'audit_date': date}).auditDate, date);
    }
    for (final date in [
      '0999-12-31',
      '10000-01-01',
      '1900-02-29',
      '2024-04-31',
      '2024-2-01',
      '2024-01-01\n',
    ]) {
      expect(
        () => draft({'audit_date': date}),
        throwsA(ApiFailure.invalidInput),
      );
    }
  });
  test(
    'strict six-key JSON rejects mass assignment, omission and wrong types',
    () {
      for (final value in [
        null,
        [],
        {...fields(), 'audited_by_user_id': 7},
        {...fields()}..remove('remarks'),
        {...fields(), 'remarks': 4},
        {...fields(), 'driver_name': null},
      ]) {
        expect(
          () => AuditDraft.fromJson(value),
          throwsA(ApiFailure.invalidInput),
        );
      }
    },
  );
  test(
    'named factory emits immutable six-key payload with nullable optionals',
    () {
      final result = AuditDraft(
        driverName: ' Driver ',
        auditDate: '2024-02-29',
        station: ' Station ',
        plateNumber: ' ABC ',
      ).toCreateJson();
      expect(result, fields());
      expect(() => result['remarks'] = 'changed', throwsUnsupportedError);
    },
  );
  test('diff omits unchanged fields and explicitly clears optional values', () {
    final baseline = draft({'helper_name': 'Helper', 'remarks': 'Remark'});
    final patch = draft({'remarks': 'Remark', 'station': 'New'}).diff(baseline);
    expect(patch, {'helper_name': null, 'station': 'New'});
    expect(() => patch['station'] = 'Other', throwsUnsupportedError);
    expect(() => baseline.diff(baseline), throwsA(ApiFailure.invalidInput));
  });
  test('pending create freezes payload and one unique UUIDv4 for retries', () {
    final attempt = PendingAuditCreate(draft({}));
    expect(
      attempt.key,
      matches(
        RegExp(
          r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        ),
      ),
    );
    final key = attempt.key;
    expect(attempt.key, key);
    expect(attempt.payload, fields());
    expect(
      () => attempt.payload['driver_name'] = 'Other',
      throwsUnsupportedError,
    );
    expect(PendingAuditCreate(draft({})).key, isNot(key));
  });
}
