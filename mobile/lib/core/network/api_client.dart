import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'api_origin.dart';
import 'api_failure.dart';
import 'json_contract.dart';
import '../../features/auth/models.dart';
import '../../features/audits/models.dart';
import '../../features/audits/audit_draft.dart';
import '../../features/audits/audit_history_models.dart';

class ApiClient {
  ApiClient(ApiOrigin origin, {http.Client Function()? clientFactory})
    : _origin = Uri.parse(origin.value),
      _clientFactory = clientFactory ?? http.Client.new;
  static const _bodyLimit = 2 * 1024 * 1024;
  final Uri _origin;
  final http.Client Function() _clientFactory;
  final _pending = <_PendingRequest>{};

  Future<void> health() async {
    final response = await _request('GET', '/health');
    final json = jsonObject(response.json);
    if (json.length != 1 || json['status'] != 'ok') throw ApiFailure.protocol;
  }

  Future<SessionLease> login(String username, String password) async {
    final name = username.trim();
    if (name.isEmpty ||
        name.runes.length > 100 ||
        password.isEmpty ||
        password.runes.length > 128) {
      throw ApiFailure.invalidInput;
    }
    final response = await _request(
      'POST',
      '/auth/login',
      body: {'username': name, 'password': password},
    );
    return SessionLease.fromJson(response.json);
  }

  Future<AuthenticatedUser> me(String token) async =>
      AuthenticatedUser.fromJson(
        (await _request('GET', '/auth/me', token: token)).json,
      );

  Future<void> logout(String token) async {
    await _request('POST', '/auth/logout', token: token, expectedStatus: 204);
  }

  Future<AuditPage> audits(
    String token,
    AuditQuery query, {
    AuditAccess access = AuditAccess.active,
  }) async => AuditPage.fromJson(
    (await _request(
      'GET',
      '/audits',
      token: token,
      query: {
        ...query.toQueryParameters(),
        if (access.includeDeleted) 'include_deleted': 'true',
      },
    )).json,
    query,
    access: access,
  );

  Future<AuditRecord> audit(
    String token,
    int id, {
    AuditAccess access = AuditAccess.active,
  }) async {
    if (id < 1) throw ApiFailure.invalidInput;
    final response = await _request(
      'GET',
      '/audits/$id',
      token: token,
      query: access.includeDeleted ? {'include_deleted': 'true'} : null,
    );
    final etag = response.headers['etag'];
    if (etag == null) throw ApiFailure.protocol;
    final record = AuditRecord.fromJson(
      response.json,
      etag: etag,
      access: access,
    );
    if (record.id != id) throw ApiFailure.protocol;
    return record;
  }

  Future<AuditMutationResult> createAudit(
    String token,
    PendingAuditCreate attempt,
  ) async {
    final response = await _request(
      'POST',
      '/audits',
      token: token,
      body: attempt.payload,
      idempotencyKey: attempt.key,
      acceptedStatuses: const {200, 201},
    );
    return AuditMutationResult(
      _record(response),
      replayed: response.status == 200,
    );
  }

  Future<AuditRecord> updateAudit(
    String token,
    int id,
    String etag,
    AuditPatch patch,
  ) async {
    final version = _precondition(id, etag);
    final response = await _request(
      'PATCH',
      '/audits/$id',
      token: token,
      body: patch.payload,
      ifMatch: etag,
    );
    final record = _record(response);
    if (record.id != id || record.version != version + 1) {
      throw ApiFailure.protocol;
    }
    return record;
  }

  Future<void> deleteAudit(String token, int id, String etag) async {
    _precondition(id, etag);
    await _request(
      'DELETE',
      '/audits/$id',
      token: token,
      ifMatch: etag,
      expectedStatus: 204,
    );
  }

  Future<AuditHistoryPage> auditHistory(
    String token,
    int id, {
    int page = 1,
    AuditAccess access = AuditAccess.active,
  }) async {
    if (id < 1 || page < 1 || page > 10000) throw ApiFailure.invalidInput;
    final response = await _request(
      'GET',
      '/audits/$id/history',
      token: token,
      query: {
        'page': '$page',
        'page_size': '${AuditHistoryPage.pageSize}',
        if (access.includeDeleted) 'include_deleted': 'true',
      },
    );
    return AuditHistoryPage.fromJson(
      response.json,
      auditId: id,
      page: page,
      access: access,
    );
  }

  static AuditRecord _record(_ApiResponse response) {
    final etag = response.headers['etag'];
    if (etag == null) throw ApiFailure.protocol;
    return AuditRecord.fromJson(response.json, etag: etag);
  }

  static int _precondition(int id, String etag) {
    final match = RegExp(r'^"[1-9][0-9]{0,9}"$').firstMatch(etag);
    if (id < 1 || match == null || match.end != etag.length) {
      throw ApiFailure.invalidInput;
    }
    return int.parse(etag.substring(1, etag.length - 1));
  }

  /// Cancels only currently running operations; subsequent requests are allowed.
  void cancelAll() {
    for (final operation in _pending.toList()) {
      operation.cancel(ApiFailure.canceled);
    }
  }

  Future<_ApiResponse> _request(
    String method,
    String path, {
    String? token,
    Map<String, String>? query,
    Map<String, Object?>? body,
    int expectedStatus = 200,
    Set<int>? acceptedStatuses,
    String? idempotencyKey,
    String? ifMatch,
  }) async {
    if (token != null && !validBearer(token)) throw ApiFailure.invalidInput;
    _PendingRequest? operation;
    Timer? deadline;
    try {
      operation = _PendingRequest(_clientFactory());
      _pending.add(operation);
      deadline = Timer(
        const Duration(seconds: 20),
        () => operation!.cancel(ApiFailure.timeout),
      );
      final request =
          http.AbortableRequest(
              method,
              _origin.replace(path: path, queryParameters: query),
              abortTrigger: operation.abort.future,
            )
            ..followRedirects = false
            ..headers['accept'] = 'application/json';
      if (token != null) request.headers['authorization'] = 'Bearer $token';
      if (idempotencyKey != null) {
        request.headers['idempotency-key'] = idempotencyKey;
      }
      if (ifMatch != null) request.headers['if-match'] = ifMatch;
      if (body != null) {
        request.headers['content-type'] = 'application/json; charset=utf-8';
        request.body = jsonEncode(body);
      }
      return await Future.any([
        _consume(operation, request, acceptedStatuses ?? {expectedStatus}),
        operation.canceled.future,
      ]);
    } on ApiFailure {
      rethrow;
    } on FormatException {
      throw ApiFailure.protocol;
    } catch (_) {
      throw ApiFailure.network;
    } finally {
      deadline?.cancel();
      if (operation != null) {
        _pending.remove(operation);
        operation.close();
      }
    }
  }

  Future<_ApiResponse> _consume(
    _PendingRequest operation,
    http.BaseRequest request,
    Set<int> acceptedStatuses,
  ) async {
    final response = await operation.client.send(request);
    if (operation.closed) {
      await response.stream.listen(null).cancel();
      throw ApiFailure.canceled;
    }
    // The server is never allowed to redirect either credentials or public calls.
    if (response.statusCode >= 300 && response.statusCode < 400) {
      throw ApiFailure.fromStatus(response.statusCode);
    }
    if (response.contentLength != null &&
        response.contentLength! > _bodyLimit) {
      throw ApiFailure.protocol;
    }
    final bytes = BytesBuilder(copy: false);
    final bodyDone = Completer<void>();
    operation.subscription = response.stream.listen(
      (chunk) {
        if (operation.closed || bodyDone.isCompleted) return;
        if (bytes.length + chunk.length > _bodyLimit) {
          operation.cancel(ApiFailure.protocol);
          return;
        }
        bytes.add(chunk);
      },
      onError: (Object error, StackTrace stack) {
        if (!bodyDone.isCompleted) bodyDone.completeError(error, stack);
      },
      onDone: () {
        if (!bodyDone.isCompleted) bodyDone.complete();
      },
      cancelOnError: true,
    );
    await Future.any<void>([bodyDone.future, operation.canceled.future]);
    if (!acceptedStatuses.contains(response.statusCode)) {
      final retry = int.tryParse(response.headers['retry-after'] ?? '');
      throw ApiFailure.fromStatus(
        response.statusCode,
        retryAfter: retry == null
            ? null
            : Duration(seconds: retry.clamp(0, 300)),
      );
    }
    if (response.statusCode == 204) {
      return _ApiResponse(null, response.headers, response.statusCode);
    }
    final contentType = response.headers['content-type']
        ?.split(';')
        .first
        .trim()
        .toLowerCase();
    if (contentType != 'application/json') throw ApiFailure.protocol;
    return _ApiResponse(
      jsonDecode(utf8.decode(bytes.takeBytes())),
      response.headers,
      response.statusCode,
    );
  }
}

class _ApiResponse {
  const _ApiResponse(this.json, this.headers, this.status);
  final Object? json;
  final Map<String, String> headers;
  final int status;
}

class _PendingRequest {
  _PendingRequest(this.client);
  final http.Client client;
  final abort = Completer<void>();
  final canceled = Completer<Never>();
  StreamSubscription<List<int>>? subscription;
  bool closed = false;
  void cancel(ApiFailure reason) {
    if (closed) return;
    // Complete the safe failure before aborting the socket, so transport errors
    // caused by the abort cannot replace the requested cancellation reason.
    canceled.completeError(reason);
    close();
  }

  void close() {
    if (closed) return;
    closed = true;
    if (!abort.isCompleted) abort.complete();
    // Cleanup must never replace a sanitized request result or produce an
    // unhandled asynchronous error from a transport implementation.
    try {
      final cleanup = subscription?.cancel();
      if (cleanup != null) {
        unawaited(cleanup.catchError((Object _) {}));
      }
    } catch (_) {
      // Some stream implementations throw synchronously during cancellation.
    }
    try {
      client.close();
    } catch (_) {
      // Closing is best effort after aborting the request.
    }
  }
}
