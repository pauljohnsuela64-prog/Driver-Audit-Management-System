import 'models.dart';

abstract interface class OfflineRepository {
  Future<LocalProfile?> profile();
  Future<LocalProfile> saveProfile(String name);
  Future<AuditPage> list(AuditFilter filter);
  Future<LocalAudit> read(String id);
  Future<LocalAudit> create(String id, AuditValues values);
  Future<LocalAudit> update(String id, int revision, AuditValues values);
  Future<LocalAudit> archive(String id, int revision);
  Future<List<LocalEvent>> history(
    String id, {
    int page = 1,
    int pageSize = 10,
  });
  Future<void> close();
}
