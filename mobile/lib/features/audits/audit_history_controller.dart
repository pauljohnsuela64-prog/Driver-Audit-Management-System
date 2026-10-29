import 'package:flutter/foundation.dart';

import '../../core/network/api_failure.dart';
import '../auth/session_controller.dart';
import 'audit_history_models.dart';
import 'audit_permissions.dart';

/// Owns the displayed page and suppresses late reads across route/session changes.
class AuditHistoryController extends ChangeNotifier {
  AuditHistoryController(
    this._session,
    this.auditId, {
    this.includeArchived = false,
  }) : _generation = _session.generation {
    _unavailable = !_authorized || auditId < 1;
    _session.addListener(_sessionChanged);
  }
  final SessionController _session;
  final int auditId;
  final bool includeArchived;
  final int _generation;
  int _request = 0;
  bool _disposed = false;
  bool _loading = false;
  bool _unavailable = false;
  int _pageNumber = 1;
  AuditHistoryPage? _page;
  String? _error;
  bool get loading => _loading;
  bool get unavailable => _unavailable;
  int get pageNumber => _pageNumber;
  AuditHistoryPage? get page => _page;
  String? get error => _error;
  bool get _authorized =>
      _session.generation == _generation &&
      _session.user != null &&
      (!includeArchived || AuditPermissions.canIncludeArchived(_session.user!));

  void _sessionChanged() {
    if (_authorized) return;
    _request++;
    _page = null;
    _error = null;
    _loading = false;
    _unavailable = true;
    if (!_disposed) notifyListeners();
  }

  Future<void> load(int number) async {
    if (_disposed ||
        !_authorized ||
        _unavailable ||
        number < 1 ||
        number > 10000) {
      return;
    }
    final request = ++_request;
    _pageNumber = number;
    _page = null;
    _error = null;
    _loading = true;
    notifyListeners();
    bool current() => !_disposed && request == _request && _authorized;
    try {
      final result = await _session.fetchAuditHistory(
        auditId,
        page: number,
        includeDeleted: includeArchived,
      );
      if (current()) _page = result;
    } on ApiFailure catch (failure) {
      if (!current()) return;
      _error = failure.message;
      if (failure.status == 403 || failure.status == 404) {
        _unavailable = true;
        if (failure.status == 403) await _session.verifyOnResume();
      }
    } catch (_) {
      if (current()) _error = 'Unable to load audit history. Try again.';
    } finally {
      if (current()) {
        _loading = false;
        notifyListeners();
      }
    }
  }

  Future<void> refresh() => load(1);
  Future<void> retry() => load(_pageNumber);
  Future<void> previous() async {
    if (!_loading && _pageNumber > 1) await load(_pageNumber - 1);
  }

  Future<void> next() async {
    if (!_loading && _page != null && _pageNumber < _page!.totalPages) {
      await load(_pageNumber + 1);
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _request++;
    _page = null;
    _session.removeListener(_sessionChanged);
    super.dispose();
  }
}
