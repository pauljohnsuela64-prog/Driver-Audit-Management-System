import 'package:flutter/foundation.dart';

import '../auth/session_controller.dart';
import 'audit_draft.dart';
import 'audit_mutation_controller.dart';
import 'audit_permissions.dart';
import 'models.dart';

class AuditFormResult {
  const AuditFormResult(this.record, {this.replayed = false});
  final AuditRecord record;
  final bool replayed;
}

class AuditFormController extends ChangeNotifier {
  AuditFormController({
    required this.session,
    this.record,
    PendingAuditCreate? pendingCreate,
  }) : generation = session.generation {
    final now = DateTime.now();
    values = Map.of(
      pendingCreate?.payload ??
          (record == null
              ? {
                  'driver_name': '',
                  'helper_name': '',
                  'audit_date':
                      '${now.year.toString().padLeft(4, '0')}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}',
                  'station': '',
                  'plate_number': '',
                  'remarks': '',
                }
              : {
                  'driver_name': record!.driverName,
                  'helper_name': record!.helperName,
                  'audit_date': record!.auditDate,
                  'station': record!.station,
                  'plate_number': record!.plateNumber,
                  'remarks': record!.remarks,
                }),
    );
    initial = Map.of(values);
    if (pendingCreate != null &&
        session.mutations.state.phase == AuditMutationPhase.conflict) {
      requiresReload = true;
      message = 'This create attempt conflicts with the server state. Close this form before reviewing the pending attempt.';
    }
    session.addListener(_sessionChanged);
    if (!active) _sessionChanged();
  }
  final SessionController session;
  final AuditRecord? record;
  final int generation;
  late final Map<String, Object?> values;
  late final Map<String, Object?> initial;
  bool busy = false, closed = false, requiresReload = false;
  bool accessLost = false;
  String? message;
  bool get active =>
      !closed &&
      !accessLost &&
      session.generation == generation &&
      session.user != null;
  bool get frozen => record == null && session.mutations.pendingCreate != null;
  bool get dirty => values.keys.any((key) => values[key] != initial[key]);
  bool get canSave =>
      active &&
      !busy &&
      !requiresReload &&
      !session.mutations.busy &&
      (record == null
          ? AuditPermissions.canCreate(session.user!)
          : AuditPermissions.canEdit(session.user!, record!));
  String? validateField(String key, String? value) {
    try {
      AuditPatch.fromJson({key: value});
      return null;
    } catch (_) {
      return key == 'audit_date'
          ? 'Enter a valid date as YYYY-MM-DD (1000-9999).'
          : '${key.replaceAll('_', ' ')}: ${key == 'helper_name' || key == 'remarks' ? 'optional' : 'required'}, maximum ${const {'driver_name': 200, 'helper_name': 200, 'station': 150, 'plate_number': 30, 'remarks': 10000}[key]} characters.';
    }
  }

  void _sessionChanged() {
    if (!active) {
      values.updateAll((key, value) => '');
      initial.clear();
      closed = true;
      message = null;
      notifyListeners();
    }
  }

  Future<AuditFormResult?> save() async {
    if (!canSave) return null;
    busy = true;
    message = null;
    notifyListeners();
    try {
      if (!active) return null;
      if (record == null) {
        final result = frozen
            ? await session.mutations.retryCreate()
            : await session.createAudit(
                PendingAuditCreate(AuditDraft.fromJson(values)),
              );
        if (!active) return null;
        return AuditFormResult(result.record, replayed: result.replayed);
      }
      final draft = AuditDraft.fromJson(values);
      final baseline = AuditDraft.fromJson(initial);
      if (mapEquals(draft.toCreateJson(), baseline.toCreateJson())) {
        message = 'No changes to save.';
        return null;
      }
      if (record!.etag == null) {
        requiresReload = true;
        message = 'Close and reload this audit before saving.';
        return null;
      }
      final saved = await session.updateAudit(
        record!.id,
        record!.etag!,
        AuditPatch.fromJson(draft.diff(baseline)),
      );
      return active ? AuditFormResult(saved) : null;
    } on AuditMutationFailure catch (error) {
      if (active) {
        if (error.failure.status == 403 || error.failure.status == 404) {
          accessLost = true;
          values.updateAll((key, value) => '');
          initial.clear();
          notifyListeners();
          if (error.failure.status == 403) await session.verifyOnResume();
          return null;
        }
        if (record == null &&
            error.failure.status == 422 &&
            session.mutations.canCorrectRejectedCreate) {
          session.mutations.releaseRejectedCreate();
        }
        requiresReload =
            error.failure.status == 409 ||
            error.failure.status == 412 ||
            (record != null && error.unconfirmed);
        message = requiresReload
            ? 'The audit may have changed. Your draft is retained. Close and reload before editing again.'
            : frozen
            ? 'The server may already have saved this audit. Retry uses the same saved attempt.'
            : error.failure.message;
      }
      return null;
    } catch (_) {
      if (active) message = 'Check the entered values and try again.';
      return null;
    } finally {
      busy = false;
      if (!closed) notifyListeners();
    }
  }

  @override
  void dispose() {
    session.removeListener(_sessionChanged);
    values.clear();
    initial.clear();
    closed = true;
    super.dispose();
  }
}
