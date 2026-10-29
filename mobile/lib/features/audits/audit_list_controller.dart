import 'package:flutter/foundation.dart';

import '../../core/network/api_failure.dart';
import '../auth/session_controller.dart';
import 'models.dart';
import 'audit_permissions.dart';

class AuditListController extends ChangeNotifier {
  AuditListController(this._session) : _generation = _session.generation {
    _session.addListener(_sessionChanged);
  }
  final SessionController _session;
  int _generation;
  int _request = 0;
  bool _disposed = false;
  AuditQuery _query = AuditQuery();
  AuditPage? _page;
  String? _error;
  bool _loading = false;
  bool _includeArchived = false;
  bool get includeArchived => _includeArchived;
  bool get canIncludeArchived =>
      _session.user != null &&
      AuditPermissions.canIncludeArchived(_session.user!);

  Future<void> setIncludeArchived(bool value) async {
    if (value && !canIncludeArchived) return;
    if (_includeArchived == value) return;
    _includeArchived = value;
    _page = null;
    await refresh();
  }

  AuditQuery get query => _query;
  AuditPage? get page => _page;
  String? get error => _error;
  bool get stale => _page != null && _error != null;
  bool get loading => _loading;

  void _sessionChanged() {
    if (_generation == _session.generation &&
        (!_includeArchived || canIncludeArchived)) {
      if (!_disposed) notifyListeners();
      return;
    }
    _generation = _session.generation;
    _request++;
    _page = null;
    _includeArchived = false;
    _error = null;
    _loading = false;
    _query = AuditQuery();
    if (!_disposed) notifyListeners();
  }

  Future<void> apply(AuditQuery query) async {
    if (_disposed) return;
    final request = ++_request;
    final generation = _session.generation;
    // Retain stale rows only when retrying exactly the displayed query. Rows
    // from another page/filter must not be labeled as the requested result.
    if (!mapEquals(_query.toQueryParameters(), query.toQueryParameters())) {
      _page = null;
    }
    _query = query;
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      final includeArchived = _includeArchived;
      final result = await _session.fetchAudits(
        query,
        includeDeleted: includeArchived,
      );
      if (includeArchived && !canIncludeArchived) return;
      if (_disposed ||
          request != _request ||
          generation != _session.generation) {
        return;
      }
      _page = result;
    } on ApiFailure catch (failure) {
      if (_disposed ||
          request != _request ||
          generation != _session.generation) {
        return;
      }
      _error = failure.message;
    } catch (_) {
      if (_disposed ||
          request != _request ||
          generation != _session.generation) {
        return;
      }
      _error = 'Unable to load audits. Try again.';
    } finally {
      if (!_disposed &&
          request == _request &&
          generation == _session.generation) {
        _loading = false;
        notifyListeners();
      }
    }
  }

  Future<void> refresh() => apply(_query.copyWith(page: 1));
  Future<void> next() async {
    if (!_loading &&
        _page != null &&
        _query.page < _page!.totalPages &&
        _query.page < 10000) {
      await apply(_query.copyWith(page: _query.page + 1));
    }
  }

  Future<void> previous() async {
    if (!_loading && _query.page > 1) {
      await apply(_query.copyWith(page: _query.page - 1));
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _request++;
    _session.removeListener(_sessionChanged);
    _page = null;
    super.dispose();
  }
}
