import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'api_origin.dart';
import 'api_failure.dart';
import 'json_contract.dart';
import '../../features/auth/models.dart';
import '../../features/audits/models.dart';

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

  Future<AuditPage> audits(String token, AuditQuery query) async =>
      AuditPage.fromJson(
        (await _request(
          'GET',
          '/audits',
          token: token,
          query: query.toQueryParameters(),
        )).json,
        query,
      );

  Future<AuditRecord> audit(String token, int id) async {
    if (id < 1) throw ApiFailure.invalidInput;
    final response = await _request('GET', '/audits/$id', token: token);
    final etag = response.headers['etag'];
    if (etag == null) throw ApiFailure.protocol;
    final record = AuditRecord.fromJson(response.json, etag: etag);
    if (record.id != id) throw ApiFailure.protocol;
    return record;
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
    Map<String, String>? body,
    int expectedStatus = 200,
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
      if (body != null) {
        request.headers['content-type'] = 'application/json; charset=utf-8';
        request.body = jsonEncode(body);
      }
      return await Future.any([
        _consume(operation, request, expectedStatus),
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
    int expectedStatus,
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
    if (response.statusCode != expectedStatus) {
      final retry = int.tryParse(response.headers['retry-after'] ?? '');
      throw ApiFailure.fromStatus(
        response.statusCode,
        retryAfter: retry == null
            ? null
            : Duration(seconds: retry.clamp(0, 300)),
      );
    }
    if (expectedStatus == 204) return _ApiResponse(null, response.headers);
    final contentType = response.headers['content-type']
        ?.split(';')
        .first
        .trim()
        .toLowerCase();
    if (contentType != 'application/json') throw ApiFailure.protocol;
    return _ApiResponse(
      jsonDecode(utf8.decode(bytes.takeBytes())),
      response.headers,
    );
  }
}

class _ApiResponse {
  const _ApiResponse(this.json, this.headers);
  final Object? json;
  final Map<String, String> headers;
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
