import '../auth/models.dart';
import 'models.dart';

/// Presentation policy; the API independently authorizes every request.
class AuditPermissions {
  static bool canCreate(AuthenticatedUser user) =>
      user.role == 'ADMIN' || user.role == 'AUDITOR';
  static bool canEdit(AuthenticatedUser user, AuditRecord record) =>
      record.deletedAt == null &&
      (user.role == 'ADMIN' ||
          (user.role == 'AUDITOR' && user.id == record.auditedByUserId));
  static bool canDelete(AuthenticatedUser user, AuditRecord record) =>
      record.deletedAt == null && user.role == 'ADMIN';
  static bool canIncludeArchived(AuthenticatedUser user) =>
      user.role == 'ADMIN';
  static bool canReadHistory(AuthenticatedUser user, AuditRecord record) =>
      canCreate(user) && (record.deletedAt == null || canIncludeArchived(user));
}
