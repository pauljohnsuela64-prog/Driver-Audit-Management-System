import 'package:flutter/foundation.dart';

import '../../core/network/api_client.dart';
import '../../core/network/api_origin.dart';
import '../../core/network/api_failure.dart';
import '../audits/models.dart';
import '../audits/audit_draft.dart';
import '../audits/audit_history_models.dart';
import '../audits/audit_mutation_controller.dart';
import 'models.dart';

class SessionController extends ChangeNotifier {
  SessionController(
    ApiClient Function(ApiOrigin) apiFactory, {
    DateTime Function()? clock,
  }) : _apiFactory = apiFactory,
       _clock = clock ?? DateTime.now;
  final ApiClient Function(ApiOrigin) _apiFactory;
  final DateTime Function() _clock;
  ApiOrigin? _origin;
  AuthenticatedUser? _user;
  SessionLease? _lease;
  ApiClient? _api;
  ApiClient? _listApi;
  ApiClient? _detailApi;
  ApiClient? _mutationApi;
  ApiClient? _historyApi;
  ApiClient? _reviewApi;
  _AuditMutationOperation? _mutationOperation;
  late final AuditMutationController mutations = AuditMutationController(
    authenticated: () => !_disposed && _user != null,
    create: (attempt) =>
        _mutate((api, token) => api.createAudit(token, attempt)),
    update: (id, etag, patch) =>
        _mutate((api, token) => api.updateAudit(token, id, etag, patch)),
    delete: (id, etag) =>
        _mutate((api, token) => api.deleteAudit(token, id, etag)),
    review: _reviewAudit,
  );
  _LoginAttempt? _pendingLogin;
  bool _busy = false;
  bool _loginInProgress = false;
  bool _disposed = false;
  String? _notice;
  int _generation = 0;
  Future<void>? _resumeVerification;
  int? _resumeVerificationGeneration;

  ApiOrigin? get origin => _origin;
  AuthenticatedUser? get user => _user;
  DateTime? get expiresAt => _lease?.expiresAt;
  bool get busy => _busy;
  String? get notice => _notice;
  int get generation => _generation;
  bool get canChangeOrigin => !_disposed && !_busy && _user == null;

  void setOrigin(ApiOrigin value) {
    if (!canChangeOrigin) throw ApiFailure.busy;
    if (_origin == value) return;
    _generation++;
    _cancelProtectedRequests();
    _api = null;
    _origin = value;
    _notice = null;
    _emit();
  }

  Future<void> signIn(String username, String password) async {
    if (_disposed || _busy || _user != null) return;
    final endpoint = _origin;
    if (endpoint == null) {
      _notice = 'Choose a connection before signing in.';
      _emit();
      return;
    }
    final requestGeneration = ++_generation;
    _busy = true;
    _loginInProgress = true;
    _notice = null;
    _emit();
    ApiClient? api;
    SessionLease? candidate;
    _LoginAttempt? attempt;
    var adopted = false;
    try {
      // Each attempt owns its transport, including any late revocation. An old
      // attempt can never cancel a subsequent session's requests.
      api = _apiFactory(endpoint);
      attempt = _LoginAttempt(api);
      _pendingLogin = attempt;
      candidate = await api.login(username, password);
      attempt.lease = candidate;
      if (!_current(requestGeneration)) return;
      if (!_clock().toUtc().isBefore(candidate.expiresAt)) {
        throw ApiFailure.fromStatus(401);
      }
      final identity = await api.me(candidate.accessToken);
      if (!_current(requestGeneration)) return;
      if (!_clock().toUtc().isBefore(candidate.expiresAt)) {
        throw ApiFailure.fromStatus(401);
      }
      _lease = candidate;
      _user = identity;
      _api = api;
      adopted = true;
    } on ApiFailure catch (failure) {
      if (_current(requestGeneration)) _notice = failure.message;
    } catch (_) {
      if (_current(requestGeneration)) _notice = ApiFailure.network.message;
    } finally {
      // Cancellation cannot prove that the server did not issue a token. Keep
      // the bounded original response observable and revoke any known lease.
      if (!adopted && candidate != null && api != null) {
        await _revoke(api, candidate);
      }
      if (identical(_pendingLogin, attempt)) _pendingLogin = null;
      if (_current(requestGeneration)) {
        _busy = false;
        _loginInProgress = false;
        _emit();
      }
    }
  }

  void cancelSignIn() {
    if (_disposed || !_loginInProgress) return;
    _generation++;
    // A known issued token can be revoked now; stop its identity check. If the
    // login response is still unknown, observe only that bounded old response.
    if (_pendingLogin?.lease != null) _pendingLogin!.api.cancelAll();
    _pendingLogin = null;
    _busy = false;
    _loginInProgress = false;
    _notice = 'Sign-in canceled.';
    _emit();
  }

  Future<void> signOut() async {
    if (_disposed) return;
    if (_loginInProgress) {
      cancelSignIn();
      return;
    }
    if (_busy && _user == null) return;
    final api = _api;
    final lease = _lease;
    final auditUnconfirmed =
        _mutationOperation != null ||
        mutations.pendingCreate != null ||
        mutations.state.phase == AuditMutationPhase.unknown;
    final requestGeneration = ++_generation;
    _cancelProtectedRequests();
    _api = null;
    _user = null;
    _lease = null;
    _notice = auditUnconfirmed
        ? 'Signed out. An audit save may have completed; check Audits after signing in again.'
        : null;
    _busy = api != null && lease != null;
    _emit();
    if (api == null || lease == null) return;
    final confirmed = await _revoke(api, lease);
    if (!_current(requestGeneration)) return;
    _busy = false;
    if (!confirmed) {
      _notice =
          '${_notice ?? 'Signed out.'} Server revocation could not be confirmed.';
    }
    _emit();
  }

  Future<void> verifyOnResume() {
    final pending = _resumeVerification;
    if (pending != null && _resumeVerificationGeneration == _generation) {
      return pending;
    }
    final verification = _verifyOnResume();
    _resumeVerification = verification;
    _resumeVerificationGeneration = _generation;
    return verification.whenComplete(() {
      if (identical(_resumeVerification, verification)) {
        _resumeVerification = null;
        _resumeVerificationGeneration = null;
      }
    });
  }

  Future<void> _verifyOnResume() async {
    if (_disposed || _user == null || _busy) return;
    final SessionLease lease;
    try {
      lease = _requireLease();
    } on ApiFailure {
      return;
    }
    final api = _api!;
    final requestGeneration = _generation;
    _busy = true;
    _emit();
    try {
      final identity = await api.me(lease.accessToken);
      if (!_current(requestGeneration)) return;
      _requireLease();
      _user = identity;
    } on ApiFailure catch (failure) {
      if (_current(requestGeneration)) {
        _invalidate(failure.message);
        if (failure.code == 'unsupported_role') await _revoke(api, lease);
      }
    } catch (_) {
      if (_current(requestGeneration)) _invalidate(ApiFailure.network.message);
    } finally {
      if (_current(requestGeneration)) {
        _busy = false;
        _emit();
      }
    }
  }

  Future<AuditPage> fetchAudits(AuditQuery query) async {
    _requireLease();
    cancelAuditList();
    final api = _apiFactory(_origin!);
    _listApi = api;
    try {
      return await _read(
        api,
        (client, lease) => client.audits(lease.accessToken, query),
      );
    } finally {
      if (identical(_listApi, api)) _listApi = null;
    }
  }

  Future<AuditMutationResult> createAudit(PendingAuditCreate attempt) async =>
      mutations.create(attempt);
  Future<AuditRecord> updateAudit(
    int id,
    String etag,
    AuditPatch patch,
  ) async => mutations.update(id, etag, patch);
  Future<void> deleteAudit(int id, String etag) async =>
      mutations.delete(id, etag);
  Future<AuditRecord> reviewMutation() async => mutations.reviewLatest();
  void cancelAuditMutation() {
    _mutationOperation?.canceled = true;
    _mutationApi?.cancelAll();
  }

  Future<void> _awaitResume(int generation) async {
    final pending = _resumeVerificationGeneration == generation
        ? _resumeVerification
        : null;
    if (pending != null) await pending;
    if (!_current(generation)) throw ApiFailure.canceled;
    _requireLease();
    if (_busy) throw ApiFailure.busy;
  }

  Future<T> _mutate<T>(Future<T> Function(ApiClient, String) operation) async {
    final generation = _generation;
    if (_mutationOperation != null) {
      throw const AuditMutationFailure(ApiFailure.busy, unconfirmed: false);
    }
    final marker = _AuditMutationOperation();
    _mutationOperation = marker;
    var dispatched = false;
    try {
      await _awaitResume(generation);
      // Awaiting a completed preflight still yields. A resume can start in that
      // gap, so check the current shared verification again before dispatch.
      while (_resumeVerificationGeneration == generation &&
          _resumeVerification != null) {
        await _awaitResume(generation);
      }
      if (marker.canceled) throw ApiFailure.canceled;
      final lease = _requireLease();
      final api = _apiFactory(_origin!);
      _mutationApi = api;
      dispatched = true;
      final result = await operation(api, lease.accessToken);
      // A resume may have started while the write was in flight. Do not publish
      // protected results until that identity check has also completed.
      await _awaitResume(generation);
      if (marker.canceled) throw ApiFailure.canceled;
      return result;
    } on ApiFailure catch (error) {
      if (_current(generation) && error.status == 401) {
        _invalidate(error.message);
      }
      final safe = _current(generation) ? error : ApiFailure.canceled;
      final unknown =
          dispatched &&
          (safe.code == 'protocol' ||
              safe.status == null && safe.code != 'invalid_input' ||
              (safe.status ?? 0) >= 500);
      throw AuditMutationFailure(safe, unconfirmed: unknown);
    } catch (_) {
      throw AuditMutationFailure(
        _current(generation) ? ApiFailure.network : ApiFailure.canceled,
        unconfirmed: dispatched,
      );
    } finally {
      if (identical(_mutationOperation, marker)) {
        _mutationApi = null;
        _mutationOperation = null;
      }
    }
  }

  Future<AuditRecord> _reviewAudit(int id, bool includeDeleted) async {
    final generation = _generation;
    await _awaitResume(generation);
    final access = includeDeleted
        ? AuditAccess.archivedFor(_user!)
        : AuditAccess.active;
    _reviewApi?.cancelAll();
    final api = _apiFactory(_origin!);
    _reviewApi = api;
    try {
      return await _read(
        api,
        (client, lease) => client.audit(lease.accessToken, id, access: access),
      );
    } finally {
      if (identical(_reviewApi, api)) _reviewApi = null;
    }
  }

  Future<AuditHistoryPage> fetchAuditHistory(
    int id, {
    int page = 1,
    bool includeDeleted = false,
  }) async {
    final generation = _generation;
    await _awaitResume(generation);
    final access = includeDeleted
        ? AuditAccess.archivedFor(_user!)
        : AuditAccess.active;
    _historyApi?.cancelAll();
    final api = _apiFactory(_origin!);
    _historyApi = api;
    try {
      return await _read(
        api,
        (client, lease) => client.auditHistory(
          lease.accessToken,
          id,
          page: page,
          access: access,
        ),
      );
    } finally {
      if (identical(_historyApi, api)) _historyApi = null;
    }
  }

  Future<AuditRecord> fetchAudit(int id) async {
    _requireLease();
    cancelAuditDetail();
    final api = _apiFactory(_origin!);
    _detailApi = api;
    try {
      return await _read(
        api,
        (client, lease) => client.audit(lease.accessToken, id),
      );
    } finally {
      if (identical(_detailApi, api)) _detailApi = null;
    }
  }

  void cancelAuditList() {
    _listApi?.cancelAll();
    _listApi = null;
  }

  void cancelAuditDetail() {
    _detailApi?.cancelAll();
    _detailApi = null;
  }

  void _cancelProtectedRequests() {
    cancelAuditList();
    cancelAuditDetail();
    _api?.cancelAll();
    _mutationApi?.cancelAll();
    _mutationApi = null;
    _mutationOperation = null;
    _historyApi?.cancelAll();
    _historyApi = null;
    _reviewApi?.cancelAll();
    _reviewApi = null;
    mutations.clearForSessionChange();
  }

  Future<T> _read<T>(
    ApiClient api,
    Future<T> Function(ApiClient, SessionLease) operation,
  ) async {
    final lease = _requireLease();
    if (_busy) throw ApiFailure.busy;
    final requestGeneration = _generation;
    try {
      final result = await operation(api, lease);
      if (!_current(requestGeneration)) throw ApiFailure.canceled;
      _requireLease();
      return result;
    } on ApiFailure catch (failure) {
      if (_current(requestGeneration) && failure.status == 401) {
        _invalidate(failure.message);
      }
      rethrow;
    }
  }

  SessionLease _requireLease() {
    final lease = _lease;
    if (_disposed || _user == null || lease == null) {
      throw ApiFailure.fromStatus(401);
    }
    if (!_clock().toUtc().isBefore(lease.expiresAt)) {
      final failure = ApiFailure.fromStatus(401);
      _invalidate(failure.message);
      throw failure;
    }
    return lease;
  }

  bool _current(int value) => !_disposed && value == _generation;
  void _invalidate(String message) {
    _generation++;
    _cancelProtectedRequests();
    _api = null;
    _lease = null;
    _user = null;
    _busy = false;
    _loginInProgress = false;
    _notice = message;
    _emit();
  }

  Future<bool> _revoke(ApiClient api, SessionLease lease) async {
    try {
      await api.logout(lease.accessToken);
      return true;
    } catch (_) {
      return false;
    }
  }

  void _emit() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _generation++;
    if (_pendingLogin?.lease != null) _pendingLogin!.api.cancelAll();
    _pendingLogin = null;
    _cancelProtectedRequests();
    _api = null;
    _lease = null;
    _user = null;
    _busy = false;
    mutations.dispose();
    super.dispose();
  }
}

class _LoginAttempt {
  _LoginAttempt(this.api);
  final ApiClient api;
  SessionLease? lease;
}

class _AuditMutationOperation {
  bool canceled = false;
}
