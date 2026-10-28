import 'package:flutter_test/flutter_test.dart';
import 'package:bhli_audit/features/auth/models.dart';
import 'package:bhli_audit/features/audits/models.dart';
import 'package:bhli_audit/features/audits/audit_permissions.dart';

AuthenticatedUser user(String role, int id) => AuthenticatedUser.fromJson({
  'id': id,
  'username': 'fictional',
  'full_name': 'Same Name',
  'role': role,
});
AuditRecord record({bool archived = false}) => AuditRecord.fromJson(
  {
    'id': 1,
    'version': 1,
    'driver_name': 'Driver',
    'helper_name': null,
    'audit_date': '2024-01-01',
    'station': 'Station',
    'plate_number': 'ABC',
    'remarks': null,
    'audited_by_name': 'Same Name',
    'audited_by_user_id': 2,
    'updated_by_user_id': null,
    'deleted_by_user_id': archived ? 1 : null,
    'deleted_at': archived ? '2024-01-02T00:00:00Z' : null,
    'created_at': '2024-01-01T00:00:00Z',
    'updated_at': '2024-01-01T00:00:00Z',
  },
  access: archived
      ? AuditAccess.archivedFor(user('ADMIN', 1))
      : AuditAccess.active,
);
void main() {
  test('archived audits are immutable with ADMIN-only history access', () {
    final audit = record(archived: true);
    for (final role in ['ADMIN', 'AUDITOR']) {
      for (final id in [2, 3]) {
        final actor = user(role, id);
        expect(AuditPermissions.canEdit(actor, audit), isFalse);
        expect(AuditPermissions.canDelete(actor, audit), isFalse);
        expect(AuditPermissions.canReadHistory(actor, audit), role == 'ADMIN');
      }
    }
  });
  test('role and stable owner ID determine active record permissions', () {
    final audit = record();
    for (final role in ['ADMIN', 'AUDITOR']) {
      for (final id in [2, 3]) {
        final actor = user(role, id);
        expect(AuditPermissions.canCreate(actor), isTrue);
        expect(
          AuditPermissions.canEdit(actor, audit),
          role == 'ADMIN' || id == 2,
        );
        expect(AuditPermissions.canDelete(actor, audit), role == 'ADMIN');
        expect(AuditPermissions.canIncludeArchived(actor), role == 'ADMIN');
        expect(AuditPermissions.canReadHistory(actor, audit), isTrue);
      }
    }
  });
}
