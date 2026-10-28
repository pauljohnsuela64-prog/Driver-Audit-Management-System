import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:bhli_audit/core/network/api_origin.dart';
import 'package:bhli_audit/core/network/api_client.dart';
import 'package:bhli_audit/core/network/api_failure.dart';
import 'package:bhli_audit/features/audits/models.dart';

import 'network_test_support.dart';

void main() {
  test('origin normalizes HTTPS and rejects credential and URL injection', () {
    expect(
      ApiOrigin.parse('HTTPS://EXAMPLE.COM:443/').value,
      'https://example.com',
    );
    expect(
      ApiOrigin.parse('https://example.com:8443').value,
      'https://example.com:8443',
    );
    for (final origin in [
      'http://example.com',
      'https://user:secret@example.com',
      'https://example.com/a',
      'https://example.com?',
      'https://example.com#',
      ' https://example.com',
      'https://example.com\n',
      'https://example.com:0',
      'https://example.com:65536',
      'https://example.com/%2f',
      'https://exa mple.com',
      'https://example.com\\@evil.test',
      'x' * 2049,
    ]) {
      expect(
        () => ApiOrigin.parse(origin),
        throwsA(isA<ApiFailure>()),
        reason: origin,
      );
    }
  });

  test(
    'cleartext requires explicit debug policy and exact loopback with port',
    () {
      expect(
        ApiOrigin.parse('http://localhost:80', allowDebugLoopback: true).value,
        'http://localhost:80',
      );
      for (final host in ['127.0.0.1', 'localhost']) {
        expect(
          ApiOrigin.parse('http://$host:8765', allowDebugLoopback: true).value,
          'http://$host:8765',
        );
        expect(
          () => ApiOrigin.parse('http://$host:8765'),
          throwsA(isA<ApiFailure>()),
        );
      }
      for (final value in [
        'http://localhost',
        'http://127.1:8765',
        'http://10.0.2.2:8765',
        'http://192.168.1.1:8765',
        'http://localhost.evil:8765',
      ]) {
        expect(
          () => ApiOrigin.parse(value, allowDebugLoopback: true),
          throwsA(isA<ApiFailure>()),
        );
      }
    },
  );

  test(
    'health sends no bearer, denies redirects and closes request client',
    () async {
      final client = RecordingClient((request) {
        expect(request.method, 'GET');
        expect(request.url.toString(), 'https://example.com/health');
        expect(request.headers.containsKey('authorization'), false);
        expect(request.followRedirects, false);
        return jsonResponse({'status': 'ok'});
      });
      await ApiClient(
        ApiOrigin.parse('https://example.com'),
        clientFactory: () => client,
      ).health();
      expect(client.closed, true);
      final redirect = RecordingClient(
        (_) => jsonResponse(
          {},
          status: 302,
          headers: {'location': 'https://evil.test/'},
        ),
      );
      await expectLater(
        ApiClient(
          ApiOrigin.parse('https://example.com'),
          clientFactory: () => redirect,
        ).health(),
        throwsA(isA<ApiFailure>()),
      );
      expect(redirect.requests.length, 1);
    },
  );

  test('health requires exact status shape', () async {
    for (final body in [
      {'status': 'down'},
      {'status': 'ok', 'other': 1},
      ['ok'],
    ]) {
      final client = RecordingClient((_) => jsonResponse(body));
      await expectLater(
        ApiClient(
          ApiOrigin.parse('https://example.com'),
          clientFactory: () => client,
        ).health(),
        throwsA(isA<ApiFailure>()),
      );
    }
  });

  test(
    'login trims username and preserves password including Unicode and spaces',
    () async {
      final client = RecordingClient((request) {
        expect(request.method, 'POST');
        expect(request.url.path, '/auth/login');
        expect(jsonDecode((request as http.Request).body), {
          'username': '🚚' * 100,
          'password': ' 🚚secret  ',
        });
        return jsonResponse(leaseJson());
      });
      final api = ApiClient(
        ApiOrigin.parse('https://example.com'),
        clientFactory: () => client,
      );
      expect(
        (await api.login(' ${'🚚' * 100} ', ' 🚚secret  ')).accessToken,
        tokenA,
      );
      await expectLater(
        api.login('🚚' * 101, 'secret'),
        throwsA(isA<ApiFailure>()),
      );
      await expectLater(
        api.login('user', '🚚' * 129),
        throwsA(isA<ApiFailure>()),
      );
      expect(client.requests.length, 1);
    },
  );

  test(
    'audit query is encoded with active-only parameters and detail keeps ETag',
    () async {
      var calls = 0;
      final clients = <RecordingClient>[];
      final api = ApiClient(
        ApiOrigin.parse('https://example.com'),
        clientFactory: () {
          final client = RecordingClient((request) {
            expect(request.headers['authorization'], 'Bearer $tokenA');
            if (calls++ == 0) {
              expect(request.url.queryParameters, {
                'station': 'A&B + 🚚',
                'sort': '-id',
                'page': '1',
                'page_size': '25',
              });
              return jsonResponse({
                'items': [auditJson()],
                'total': 1,
                'page': 1,
                'page_size': 25,
              });
            }
            expect(request.url.toString(), 'https://example.com/audits/1');
            return jsonResponse(auditJson(), headers: {'etag': '"3"'});
          });
          clients.add(client);
          return client;
        },
      );
      expect(
        (await api.audits(
          tokenA,
          AuditQuery(station: 'A&B + 🚚'),
        )).items.length,
        1,
      );
      expect((await api.audit(tokenA, 1)).etag, '"3"');
      expect(clients.every((client) => client.closed), true);
    },
  );

  test(
    'error bodies and network exceptions never escape safe typed failures',
    () async {
      for (final status in [401, 403, 404, 422, 429, 500, 503]) {
        final client = RecordingClient(
          (_) => jsonResponse(
            {
              'error': {
                'code': 'https://secret.test/password',
                'message': '<script>$tokenA</script>',
              },
            },
            status: status,
            headers: {'retry-after': '999999'},
          ),
        );
        try {
          await ApiClient(
            ApiOrigin.parse('https://example.com'),
            clientFactory: () => client,
          ).me(tokenA);
          fail('Expected safe failure');
        } on ApiFailure catch (error) {
          expect(error.status, status);
          expect(error.toString(), isNot(contains(tokenA)));
          expect(error.toString(), isNot(contains('https://')));
          if (status == 429) {
            expect(error.retryAfter!.inSeconds, lessThanOrEqualTo(300));
          }
        }
      }
      final badClient = RecordingClient(
        (_) => throw Exception('password=$tokenA'),
      );
      await expectLater(
        ApiClient(
          ApiOrigin.parse('https://example.com'),
          clientFactory: () => badClient,
        ).health(),
        throwsA(
          isA<ApiFailure>().having(
            (error) => error.toString(),
            'safe message',
            isNot(contains(tokenA)),
          ),
        ),
      );
    },
  );

  test(
    'stream limit closes the connection before accepting an oversized body',
    () async {
      final client = RecordingClient(
        (_) => http.StreamedResponse(
          Stream.value(List.filled(2 * 1024 * 1024 + 1, 32)),
          200,
        ),
      );
      await expectLater(
        ApiClient(
          ApiOrigin.parse('https://example.com'),
          clientFactory: () => client,
        ).health(),
        throwsA(isA<ApiFailure>()),
      );
      expect(client.closed, true);
    },
  );

  test(
    'malformed success JSON and mismatched detail ETag are rejected safely',
    () async {
      for (final response in [
        http.StreamedResponse(
          Stream.value(utf8.encode('<html>secret</html>')),
          200,
        ),
        jsonResponse({...auditJson(), 'id': 2}, headers: {'etag': '"3"'}),
        jsonResponse(auditJson(), headers: {'etag': '"4"'}),
      ]) {
        final client = RecordingClient((_) => response);
        await expectLater(
          ApiClient(
            ApiOrigin.parse('https://example.com'),
            clientFactory: () => client,
          ).audit(tokenA, 1),
          throwsA(isA<ApiFailure>()),
        );
        expect(client.closed, true);
      }
    },
  );

  test(
    'logout accepts exactly 204 and does not parse an empty JSON response',
    () async {
      final client = RecordingClient((request) {
        expect(request.method, 'POST');
        expect(request.url.path, '/auth/logout');
        return http.StreamedResponse(const Stream.empty(), 204);
      });
      await ApiClient(
        ApiOrigin.parse('https://example.com'),
        clientFactory: () => client,
      ).logout(tokenA);
      final wrong = RecordingClient((_) => jsonResponse({}));
      await expectLater(
        ApiClient(
          ApiOrigin.parse('https://example.com'),
          clientFactory: () => wrong,
        ).logout(tokenA),
        throwsA(isA<ApiFailure>()),
      );
    },
  );

  test('invalid bearer cannot enter request headers', () async {
    final client = RecordingClient((_) => jsonResponse(userJson()));
    final api = ApiClient(
      ApiOrigin.parse('https://example.com'),
      clientFactory: () => client,
    );
    await expectLater(
      api.me('$tokenA\r\nInjected: secret'),
      throwsA(isA<ApiFailure>()),
    );
    expect(client.requests, isEmpty);
  });

  testWidgets('deadline includes stalled response headers', (tester) async {
    final headers = Completer<http.StreamedResponse>();
    final client = RecordingClient((_) => headers.future);
    final result = expectLater(
      ApiClient(
        ApiOrigin.parse('https://example.com'),
        clientFactory: () => client,
      ).health(),
      throwsA(
        isA<ApiFailure>().having(
          (failure) => failure.code,
          'deadline',
          'timeout',
        ),
      ),
    );
    await tester.pump(const Duration(seconds: 20));
    await result;
    expect(client.closed, true);
    headers.complete(jsonResponse({'status': 'ok'}));
    await tester.pump();
  });

  test(
    '20 second deadline includes body and closes a stalled stream',
    () async {
      final body = StreamController<List<int>>();
      final client = RecordingClient(
        (_) => http.StreamedResponse(body.stream, 200),
      );
      final api = ApiClient(
        ApiOrigin.parse('https://example.com'),
        clientFactory: () => client,
      );
      final result = expectLater(
        api.health(),
        throwsA(
          isA<ApiFailure>().having(
            (failure) => failure.code,
            'deadline',
            'timeout',
          ),
        ),
      );
      await Future<void>.delayed(Duration.zero);
      body.add(utf8.encode('{'));
      await Future<void>.delayed(const Duration(seconds: 19));
      expect(client.closed, false);
      await result;
      expect(client.closed, true);
      await body.close();
    },
    timeout: const Timeout(Duration(seconds: 30)),
  );

  test('cancelAll ends stalled requests and permits future requests', () async {
    final hanging = Completer<http.StreamedResponse>();
    final first = RecordingClient((_) => hanging.future);
    final second = RecordingClient((_) => jsonResponse({'status': 'ok'}));
    var calls = 0;
    final api = ApiClient(
      ApiOrigin.parse('https://example.com'),
      clientFactory: () => calls++ == 0 ? first : second,
    );
    final canceled = expectLater(
      api.health(),
      throwsA(
        isA<ApiFailure>().having(
          (failure) => failure.code,
          'cancellation',
          'canceled',
        ),
      ),
    );
    await Future<void>.delayed(Duration.zero);
    api.cancelAll();
    await canceled;
    expect(first.closed, true);
    await api.health();
    expect(second.closed, true);
    hanging.complete(jsonResponse({'status': 'ok'}));
  });

  test('cleanup failures cannot escape the safe cancellation result', () async {
    final body = StreamController<List<int>>(
      onCancel: () => Future<void>.error(StateError('sensitive stream detail')),
    );
    final client = RecordingClient(
      (_) => http.StreamedResponse(body.stream, 200),
      onClose: () => throw StateError('sensitive close detail'),
    );
    final api = ApiClient(
      ApiOrigin.parse('https://example.com'),
      clientFactory: () => client,
    );
    final result = expectLater(
      api.health(),
      throwsA(
        isA<ApiFailure>().having(
          (failure) => failure.code,
          'safe cancellation',
          'canceled',
        ),
      ),
    );
    await Future<void>.delayed(Duration.zero);
    try {
      expect(api.cancelAll, returnsNormally);
    } finally {
      await result;
      await body.close();
    }
  });
}
