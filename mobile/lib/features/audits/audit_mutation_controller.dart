import 'package:flutter/foundation.dart';

import '../../core/network/api_failure.dart';
import 'audit_draft.dart';
import 'models.dart';

enum AuditMutationPhase {
  idle,
  sending,
  confirmed,
  unknown,
  conflict,
  forbidden,
  rejected,
}

enum AuditMutationKind { create, update, delete }

/// Safe typed failure; unconfirmed never means that the server rolled back.
class AuditMutationFailure implements Exception {
  const AuditMutationFailure(this.failure, {required this.unconfirmed});
  final ApiFailure failure;
  final bool unconfirmed;
  @override
  String toString() =>
      'AuditMutationFailure(${failure.code}, unconfirmed: $unconfirmed)';
}

class AuditMutationState {
  const AuditMutationState({
    this.phase = AuditMutationPhase.idle,
    this.kind,
    this.auditId,
    this.etag,
    this.patch,
    this.record,
    this.replayed = false,
    this.failure,
    this.latest,
  });
  final AuditMutationPhase phase;
  final AuditMutationKind? kind;
  final int? auditId;
  final String? etag;
  final AuditPatch? patch;
  final AuditRecord? record, latest;
  final bool replayed;
  final ApiFailure? failure;
}

/// Session-lifetime state for future screens. Delegates contain authentication;
/// this module never receives or stores bearer tokens, origins or passwords.
class AuditMutationController extends ChangeNotifier {
  AuditMutationController({
    required this._authenticated,
    required this._create,
    required this._update,
    required this._delete,
    required this._review,
  });
  final bool Function() _authenticated;
  final Future<AuditMutationResult> Function(PendingAuditCreate) _create;
  final Future<AuditRecord> Function(int, String, AuditPatch) _update;
  final Future<void> Function(int, String) _delete;
  final Future<AuditRecord> Function(int, bool) _review;
  AuditMutationState _state = const AuditMutationState();
  PendingAuditCreate? _pendingCreate;
  bool _createWasUnconfirmed = false;
  int _epoch = 0;
  bool _disposed = false;
  AuditMutationState get state => _state;
  PendingAuditCreate? get pendingCreate => _pendingCreate;
  bool get canCorrectRejectedCreate =>
      !busy &&
      _pendingCreate != null &&
      !_createWasUnconfirmed &&
      _state.phase == AuditMutationPhase.rejected &&
      _state.failure?.status == 422;
  void releaseRejectedCreate() {
    if (!canCorrectRejectedCreate) {
      throw const AuditMutationFailure(ApiFailure.busy, unconfirmed: false);
    }
    _pendingCreate = null;
    _createWasUnconfirmed = false;
    _set(const AuditMutationState());
  }

  bool get busy => _state.phase == AuditMutationPhase.sending;

  void _available({bool retry = false}) {
    if (_disposed || !_authenticated()) {
      throw AuditMutationFailure(
        ApiFailure.fromStatus(401),
        unconfirmed: false,
      );
    }
    if (busy ||
        (!retry &&
            (_pendingCreate != null ||
                {
                  AuditMutationPhase.unknown,
                  AuditMutationPhase.conflict,
                }.contains(_state.phase)))) {
      throw const AuditMutationFailure(ApiFailure.busy, unconfirmed: false);
    }
  }

  Future<AuditMutationResult> create(PendingAuditCreate attempt) {
    _available(retry: identical(attempt, _pendingCreate));
    if (_pendingCreate == null) _createWasUnconfirmed = false;
    _pendingCreate = attempt;
    return _run(AuditMutationKind.create, () => _create(attempt));
  }

  Future<AuditMutationResult> retryCreate() {
    final attempt = _pendingCreate;
    if (attempt == null) {
      throw const AuditMutationFailure(
        ApiFailure.invalidInput,
        unconfirmed: false,
      );
    }
    return create(attempt);
  }

  Future<AuditRecord> update(int id, String etag, AuditPatch patch) {
    _available();
    return _run(
      AuditMutationKind.update,
      () => _update(id, etag, patch),
      id: id,
      etag: etag,
      patch: patch,
    );
  }

  Future<void> delete(int id, String etag) {
    _available();
    return _run(
      AuditMutationKind.delete,
      () => _delete(id, etag),
      id: id,
      etag: etag,
    );
  }

  Future<T> _run<T>(
    AuditMutationKind kind,
    Future<T> Function() operation, {
    int? id,
    String? etag,
    AuditPatch? patch,
  }) async {
    final epoch = _epoch;
    _set(
      AuditMutationState(
        phase: AuditMutationPhase.sending,
        kind: kind,
        auditId: id,
        etag: etag,
        patch: patch,
      ),
    );
    try {
      // A listener may synchronously sign out while handling the sending state.
      // Never enter even the delegate's preflight for that abandoned session.
      if (epoch != _epoch || _disposed || !_authenticated()) {
        throw const AuditMutationFailure(
          ApiFailure.canceled,
          unconfirmed: false,
        );
      }
      final result = await operation();
      if (epoch != _epoch || _disposed) {
        throw const AuditMutationFailure(
          ApiFailure.canceled,
          unconfirmed: true,
        );
      }
      if (kind == AuditMutationKind.create) {
        _pendingCreate = null;
        _createWasUnconfirmed = false;
      }
      _set(
        AuditMutationState(
          phase: AuditMutationPhase.confirmed,
          kind: kind,
          auditId: id,
          etag: etag,
          patch: patch,
          record: result is AuditMutationResult
              ? result.record
              : result is AuditRecord
              ? result
              : null,
          replayed: result is AuditMutationResult && result.replayed,
        ),
      );
      if (epoch != _epoch || _disposed || !_authenticated()) {
        throw const AuditMutationFailure(
          ApiFailure.canceled,
          unconfirmed: true,
        );
      }
      return result;
    } on AuditMutationFailure catch (error) {
      if (epoch == _epoch && !_disposed) {
        if (kind == AuditMutationKind.create &&
            (error.unconfirmed || error.failure.status == 409)) {
          _createWasUnconfirmed = true;
        }
        final status = error.failure.status;
        final phase = status == 409 || status == 412
            ? AuditMutationPhase.conflict
            : status == 403
            ? AuditMutationPhase.forbidden
            : error.unconfirmed
            ? AuditMutationPhase.unknown
            : AuditMutationPhase.rejected;
        _set(
          AuditMutationState(
            phase: phase,
            kind: kind,
            auditId: id,
            etag: etag,
            patch: patch,
            failure: error.failure,
          ),
        );
      }
      rethrow;
    }
  }

  void abandonCreate({required bool acknowledgeDuplicateRisk}) {
    if (busy || _pendingCreate == null || !acknowledgeDuplicateRisk) {
      throw const AuditMutationFailure(ApiFailure.busy, unconfirmed: false);
    }
    _pendingCreate = null;
    _createWasUnconfirmed = false;
    _set(const AuditMutationState());
  }

  Future<AuditRecord> reviewLatest() async {
    if (busy ||
        _pendingCreate != null ||
        _state.auditId == null ||
        !_authenticated()) {
      throw const AuditMutationFailure(ApiFailure.busy, unconfirmed: false);
    }
    final epoch = _epoch;
    final prior = _state;
    _set(
      AuditMutationState(
        phase: prior.phase,
        kind: prior.kind,
        auditId: prior.auditId,
        etag: prior.etag,
        patch: prior.patch,
        failure: prior.failure,
      ),
    );
    final reviewing = _state;
    final latest = await _review(
      prior.auditId!,
      prior.kind == AuditMutationKind.delete,
    );
    if (epoch != _epoch || _disposed || !identical(_state, reviewing)) {
      throw const AuditMutationFailure(ApiFailure.canceled, unconfirmed: true);
    }
    _set(
      AuditMutationState(
        phase: prior.phase,
        kind: prior.kind,
        auditId: prior.auditId,
        etag: prior.etag,
        patch: prior.patch,
        failure: prior.failure,
        latest: latest,
      ),
    );
    if (epoch != _epoch || _disposed || !_authenticated()) {
      throw const AuditMutationFailure(ApiFailure.canceled, unconfirmed: true);
    }
    return latest;
  }

  void acknowledgeReview() {
    if (busy || _state.latest == null) {
      throw const AuditMutationFailure(ApiFailure.busy, unconfirmed: false);
    }
    _set(const AuditMutationState());
  }

  void clearRejected() {
    if (busy ||
        _pendingCreate != null ||
        _state.phase == AuditMutationPhase.unknown ||
        _state.phase == AuditMutationPhase.conflict) {
      throw const AuditMutationFailure(ApiFailure.busy, unconfirmed: false);
    }
    _set(const AuditMutationState());
  }

  void clearForSessionChange() {
    _epoch++;
    _pendingCreate = null;
    _createWasUnconfirmed = false;
    _set(const AuditMutationState());
  }

  void _set(AuditMutationState value) {
    if (!_disposed) {
      _state = value;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _epoch++;
    _pendingCreate = null;
    _createWasUnconfirmed = false;
    _state = const AuditMutationState();
    super.dispose();
  }
}
