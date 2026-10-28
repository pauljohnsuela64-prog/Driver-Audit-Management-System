import 'package:bhli_audit/core/network/api_failure.dart';
import 'package:bhli_audit/features/audits/audit_history_models.dart';
import 'package:bhli_audit/features/audits/models.dart';
import 'package:bhli_audit/features/auth/models.dart';
import 'package:flutter_test/flutter_test.dart';

import 'network_test_support.dart';

Map<String, Object?> historyEvent({String action = 'CREATE', int id = 1}) {
  final before = auditJson();
  final after = {...auditJson(), 'version': action == 'CREATE' ? 3 : 4};
  if (action == 'DELETE') {
    after['deleted_at'] = '2026-10-28T12:00:00Z';
    after['deleted_by_user_id'] = 9;
  }
  return {
    'id': id,
    'audit_id': 1,
    'actor_user_id': 9,
    'action': action,
    'before_data': action == 'CREATE' ? null : before,
    'after_data': after,
    'created_at': '2026-10-28T12:00:00Z',
  };
}

void main() {
  final admin = AuthenticatedUser.fromJson(userJson(role: 'ADMIN'));
  final auditor = AuthenticatedUser.fromJson(userJson());
  test('archived parsing requires explicit ADMIN capability', () {
    final archived = {
      ...auditJson(),
      'deleted_at': '2026-10-28T12:00:00Z',
      'deleted_by_user_id': 9,
    };
    expect(() => AuditRecord.fromJson(archived), throwsA(isA<ApiFailure>()));
    expect(() => AuditAccess.archivedFor(auditor), throwsA(isA<ApiFailure>()));
    final record = AuditRecord.fromJson(
      archived,
      access: AuditAccess.archivedFor(admin),
    );
    expect(record.deletedAt, DateTime.utc(2026, 10, 28, 12));
    expect(record.deletedByUserId, 9);
    expect(
      () => AuditRecord.fromJson({
        ...archived,
        'deleted_by_user_id': null,
      }, access: AuditAccess.archivedFor(admin)),
      throwsA(isA<ApiFailure>()),
    );
  });
  test(
    'history uses ten events, actor ID and safe immutable field projection',
    () {
      final event = historyEvent();
      (event['after_data'] as Map)['password_hash'] = 'must never surface';
      final result = AuditHistoryPage.fromJson({
        'items': [event],
        'page': 1,
        'page_size': 10,
        'total': 1,
      }, auditId: 1);
      expect(result.items.single.actorUserId, 9);
      expect(
        result.items.single.after.fields.keys,
        unorderedEquals([
          'driver_name',
          'helper_name',
          'audit_date',
          'station',
          'plate_number',
          'remarks',
          'audited_by_name',
        ]),
      );
      expect(
        result.items.single.after.fields['audited_by_name'],
        'Original Snapshot',
      );
      expect(
        () => result.items.single.after.fields['remarks'] = 'changed',
        throwsUnsupportedError,
      );
    },
  );
  test(
    'DELETE history needs archive access and correct lifecycle snapshots',
    () {
      final data = {
        'items': [historyEvent(action: 'DELETE')],
        'page': 1,
        'page_size': 10,
        'total': 1,
      };
      expect(
        () => AuditHistoryPage.fromJson(data, auditId: 1),
        throwsA(isA<ApiFailure>()),
      );
      final result = AuditHistoryPage.fromJson(
        data,
        auditId: 1,
        access: AuditAccess.archivedFor(admin),
      );
      expect(result.items.single.after.archived, true);
      expect(result.items.single.before!.archived, false);
    },
  );
  test(
    'strict history actions, identities, timestamps, snapshots and page echo',
    () {
      final mutations = <void Function(Map<String, Object?>)>[
        (e) => e['action'] = 'RESET_PASSWORD',
        (e) => e['actor_user_id'] = true,
        (e) => e['audit_id'] = 2,
        (e) => e['created_at'] = '2026-02-30T00:00:00Z',
        (e) => e['before_data'] = auditJson(),
        (e) => e['after_data'] = null,
        (e) => (e['after_data'] as Map)['id'] = 2,
      ];
      for (final mutate in mutations) {
        final e = historyEvent();
        mutate(e);
        expect(
          () => AuditHistoryPage.fromJson({
            'items': [e],
            'page': 1,
            'page_size': 10,
            'total': 1,
          }, auditId: 1),
          throwsA(isA<ApiFailure>()),
        );
      }
      for (final override in [
        {'page': 2},
        {'page_size': 25},
        {'total': -1},
        {'total': 0},
      ]) {
        expect(
          () => AuditHistoryPage.fromJson({
            'items': [historyEvent()],
            'page': 1,
            'page_size': 10,
            'total': 1,
            ...override,
          }, auditId: 1),
          throwsA(isA<ApiFailure>()),
        );
      }
      expect(
        () => AuditHistoryPage.fromJson({
          'items': [historyEvent(id: 2), historyEvent(id: 1)],
          'page': 1,
          'page_size': 10,
          'total': 2,
        }, auditId: 1),
        throwsA(isA<ApiFailure>()),
      );
    },
  );
  test('UPDATE preserves original ownership and auditor snapshot', () {
    final event = historyEvent(action: 'UPDATE');
    (event['after_data'] as Map)['audited_by_name'] = 'Changed attribution';
    expect(
      () => AuditHistoryPage.fromJson({
        'items': [event],
        'page': 1,
        'page_size': 10,
        'total': 1,
      }, auditId: 1),
      throwsA(isA<ApiFailure>()),
    );
  });
}
