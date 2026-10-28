import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:bhli_audit/core/network/api_client.dart';
import 'package:bhli_audit/core/network/api_failure.dart';
import 'package:bhli_audit/core/network/api_origin.dart';
import 'package:bhli_audit/features/auth/session_controller.dart';
import 'package:bhli_audit/features/audits/models.dart';

import 'network_test_support.dart';

void main() {
  final origin = ApiOrigin.parse('https://example.com');
  DateTime now() => DateTime.utc(2026, 10, 28, 12);

  SessionController session(
    FutureOr<http.StreamedResponse> Function(http.BaseRequest) handler, {
    DateTime Function()? clock,
  }) => SessionController(
    (value) => ApiClient(value, clientFactory: () => RecordingClient(handler)),
    clock: clock ?? now,
  )..setOrigin(origin);

  test('both roles are admitted only after me validates identity', () async {
    for (final role in ['ADMIN', 'AUDITOR']) {
      final me = Completer<http.StreamedResponse>();
      final controller = session(
        (request) => request.url.path == '/auth/login'
            ? jsonResponse(leaseJson())
            : me.future,
      );
      final signingIn = controller.signIn('fictional', 'password');
      await Future<void>.delayed(Duration.zero);
      expect(controller.busy, true);
      expect(controller.user, isNull);
      expect(controller.canChangeOrigin, false);
      expect(
        () => controller.setOrigin(ApiOrigin.parse('https://other.test')),
        throwsA(isA<ApiFailure>()),
      );
      me.complete(jsonResponse(userJson(role: role)));
      await signingIn;
      expect(controller.user!.role, role);
      expect(controller.expiresAt, DateTime.utc(2026, 10, 28, 20));
      controller.dispose();
    }
  });

  test('unknown role fails admission and revokes newly issued lease', () async {
    final paths = <String>[];
    final controller = session((request) {
      paths.add(request.url.path);
      return switch (request.url.path) {
        '/auth/login' => jsonResponse(leaseJson()),
        '/auth/me' => jsonResponse(userJson(role: 'VIEWER')),
        _ => jsonResponse(null, status: 204),
      };
    });
    await controller.signIn('fictional', 'password');
    expect(controller.user, isNull);
    expect(controller.notice, isNotNull);
    expect(paths, ['/auth/login', '/auth/me', '/auth/logout']);
    expect(controller.canChangeOrigin, true);
    controller.dispose();
  });

  test(
    'late canceled login is revoked on its original endpoint and never adopted',
    () async {
      final login = Completer<http.StreamedResponse>();
      final logoutOrigins = <String>[];
      final controller = SessionController(
        (value) => ApiClient(
          value,
          clientFactory: () => RecordingClient((request) {
            if (request.url.path == '/auth/login') return login.future;
            if (request.url.path == '/auth/logout') {
              logoutOrigins.add(request.url.host);
              expect(request.headers['authorization'], 'Bearer $tokenA');
              return jsonResponse(null, status: 204);
            }
            return jsonResponse(userJson());
          }),
        ),
        clock: now,
      )..setOrigin(origin);
      final attempt = controller.signIn('fictional', 'password');
      await Future<void>.delayed(Duration.zero);
      controller.cancelSignIn();
      controller.setOrigin(ApiOrigin.parse('https://other.test'));
      login.complete(jsonResponse(leaseJson()));
      await attempt;
      expect(controller.user, isNull);
      expect(controller.origin!.value, 'https://other.test');
      expect(logoutOrigins, ['example.com']);
      expect(controller.busy, false);
      controller.dispose();
    },
  );

  test('logout clears protected identity immediately and locks transitions until revocation', () async {
    final logout = Completer<http.StreamedResponse>();
    final controller = session(
      (request) => switch (request.url.path) {
        '/auth/login' => jsonResponse(leaseJson()),
        '/auth/me' => jsonResponse(userJson()),
        _ => logout.future,
      },
    );
    await controller.signIn('fictional', 'password');
    final generation = controller.generation;
    final signingOut = controller.signOut();
    expect(controller.user, isNull);
    expect(controller.expiresAt, isNull);
    expect(controller.generation, greaterThan(generation));
    expect(controller.busy, true);
    expect(controller.canChangeOrigin, false);
    await controller.signIn('fictional', 'password');
    expect(controller.user, isNull);
    logout.complete(
      jsonResponse({
        'error': {'code': 'unavailable'},
      }, status: 503),
    );
    await signingOut;
    expect(controller.busy, false);
    expect(controller.canChangeOrigin, true);
    expect(controller.notice, contains('revocation'));
    controller.dispose();
  });

  test('old read unauthorized cannot invalidate a newer login', () async {
    final oldRead = Completer<http.StreamedResponse>();
    var logins = 0;
    final controller = session(
      (request) => switch (request.url.path) {
        '/auth/login' => jsonResponse(
          leaseJson(token: logins++ == 0 ? tokenA : tokenB),
        ),
        '/auth/me' => jsonResponse(userJson()),
        '/auth/logout' => jsonResponse(null, status: 204),
        _ => oldRead.future,
      },
    );
    await controller.signIn('fictional', 'password');
    final oldResult = expectLater(
      controller.fetchAudits(AuditQuery()),
      throwsA(isA<ApiFailure>()),
    );
    await Future<void>.delayed(Duration.zero);
    await controller.signOut();
    await controller.signIn('fictional', 'password');
    oldRead.complete(
      jsonResponse({
        'error': {'code': 'unauthorized'},
      }, status: 401),
    );
    await oldResult;
    expect(controller.user, isNotNull);
    expect(controller.busy, false);
    controller.dispose();
  });

  test('401 clears current session while 403 preserves it', () async {
    var status = 403;
    final controller = session(
      (request) => switch (request.url.path) {
        '/auth/login' => jsonResponse(leaseJson()),
        '/auth/me' => jsonResponse(userJson()),
        _ => jsonResponse({
          'error': {'code': 'forbidden'},
        }, status: status),
      },
    );
    await controller.signIn('fictional', 'password');
    await expectLater(controller.fetchAudit(1), throwsA(isA<ApiFailure>()));
    expect(controller.user, isNotNull);
    status = 401;
    await expectLater(controller.fetchAudit(1), throwsA(isA<ApiFailure>()));
    expect(controller.user, isNull);
    expect(controller.canChangeOrigin, true);
    controller.dispose();
  });

  test(
    'local expiry clears session before another protected request',
    () async {
      var current = now();
      var requests = 0;
      final controller = session((request) {
        requests++;
        return request.url.path == '/auth/login'
            ? jsonResponse(leaseJson())
            : jsonResponse(userJson());
      }, clock: () => current);
      await controller.signIn('fictional', 'password');
      current = DateTime.utc(2026, 10, 28, 20);
      await controller.verifyOnResume();
      expect(controller.user, isNull);
      expect(requests, 2);
      controller.dispose();
    },
  );

  test(
    'resume validates current role before restoring protected access',
    () async {
      var meCalls = 0;
      final controller = session((request) {
        if (request.url.path == '/auth/login') return jsonResponse(leaseJson());
        if (request.url.path == '/auth/logout') {
          return jsonResponse(null, status: 204);
        }
        return jsonResponse(
          userJson(role: meCalls++ == 0 ? 'AUDITOR' : 'ADMIN'),
        );
      });
      await controller.signIn('fictional', 'password');
      await controller.verifyOnResume();
      expect(controller.user!.role, 'ADMIN');
      expect(meCalls, 2);
      controller.dispose();
    },
  );

  test(
    'dispose blocks late login from notifying or restoring identity',
    () async {
      final login = Completer<http.StreamedResponse>();
      var notifications = 0;
      var revoked = false;
      final controller = session((request) {
        if (request.url.path == '/auth/login') return login.future;
        revoked = true;
        return jsonResponse(null, status: 204);
      });
      controller.addListener(() {
        notifications++;
      });
      final attempt = controller.signIn('fictional', 'password');
      await Future<void>.delayed(Duration.zero);
      controller.dispose();
      final countAtDispose = notifications;
      login.complete(jsonResponse(leaseJson()));
      await attempt;
      expect(controller.user, isNull);
      expect(notifications, countAtDispose);
      expect(revoked, true);
    },
  );

  test(
    'late first login cannot replace or unlock a second pending login',
    () async {
      final first = Completer<http.StreamedResponse>();
      final second = Completer<http.StreamedResponse>();
      var logins = 0;
      final revoked = <String?>[];
      final controller = session((request) {
        if (request.url.path == '/auth/login') {
          return logins++ == 0 ? first.future : second.future;
        }
        if (request.url.path == '/auth/logout') {
          revoked.add(request.headers['authorization']);
          return jsonResponse(null, status: 204);
        }
        return jsonResponse(userJson());
      });
      final attempt1 = controller.signIn('fictional', 'password');
      controller.cancelSignIn();
      final attempt2 = controller.signIn('fictional', 'password');
      first.complete(jsonResponse(leaseJson()));
      await attempt1;
      expect(controller.user, isNull);
      expect(controller.busy, true);
      second.complete(jsonResponse(leaseJson(token: tokenB)));
      await attempt2;
      expect(controller.user, isNotNull);
      expect(revoked, ['Bearer $tokenA']);
      controller.dispose();
    },
  );

  test(
    'a session expiring during a read cannot return protected results',
    () async {
      var current = now();
      final read = Completer<http.StreamedResponse>();
      final controller = session(
        (request) => switch (request.url.path) {
          '/auth/login' => jsonResponse(leaseJson()),
          '/auth/me' => jsonResponse(userJson()),
          _ => read.future,
        },
        clock: () => current,
      );
      await controller.signIn('fictional', 'password');
      final result = expectLater(
        controller.fetchAudit(1),
        throwsA(isA<ApiFailure>()),
      );
      current = DateTime.utc(2026, 10, 28, 20);
      read.complete(jsonResponse(auditJson(), headers: {'etag': '"3"'}));
      await result;
      expect(controller.user, isNull);
      controller.dispose();
    },
  );

  test(
    'list cancellation closes only list transport while detail remains live',
    () async {
      final clients = <RecordingClient>[];
      final list = Completer<http.StreamedResponse>();
      final detail = Completer<http.StreamedResponse>();
      final controller = SessionController(
        (endpoint) => ApiClient(
          endpoint,
          clientFactory: () {
            final client = RecordingClient(
              (request) => switch (request.url.path) {
                '/auth/login' => jsonResponse(leaseJson()),
                '/auth/me' => jsonResponse(userJson()),
                '/audits' => list.future,
                _ => detail.future,
              },
            );
            clients.add(client);
            return client;
          },
        ),
        clock: now,
      )..setOrigin(origin);
      await controller.signIn('fictional', 'password');
      final listResult = expectLater(
        controller.fetchAudits(AuditQuery()),
        throwsA(
          isA<ApiFailure>().having(
            (failure) => failure.code,
            'cancellation',
            'canceled',
          ),
        ),
      );
      final detailResult = controller.fetchAudit(1);
      await Future<void>.delayed(Duration.zero);
      controller.cancelAuditList();
      expect(clients[2].closed, true);
      expect(clients[3].closed, false);
      await listResult;
      detail.complete(jsonResponse(auditJson(), headers: {'etag': '"3"'}));
      expect((await detailResult).id, 1);
      list.complete(
        jsonResponse({'items': [], 'total': 0, 'page': 1, 'page_size': 25}),
      );
      controller.dispose();
    },
  );

  test(
    'a newer list request cancels older transport without canceling detail',
    () async {
      final older = Completer<http.StreamedResponse>();
      var lists = 0;
      final controller = session(
        (request) => switch (request.url.path) {
          '/auth/login' => jsonResponse(leaseJson()),
          '/auth/me' => jsonResponse(userJson()),
          _ =>
            lists++ == 0
                ? older.future
                : jsonResponse({
                    'items': [],
                    'total': 0,
                    'page': 2,
                    'page_size': 25,
                  }),
        },
      );
      await controller.signIn('fictional', 'password');
      final first = expectLater(
        controller.fetchAudits(AuditQuery()),
        throwsA(isA<ApiFailure>()),
      );
      final next = await controller.fetchAudits(AuditQuery(page: 2));
      expect(next.page, 2);
      await first;
      older.complete(
        jsonResponse({'items': [], 'total': 0, 'page': 1, 'page_size': 25}),
      );
      controller.dispose();
    },
  );

  test(
    'cancel after lease issuance promptly revokes without waiting for me',
    () async {
      final me = Completer<http.StreamedResponse>();
      var revoked = false;
      final controller = session((request) {
        if (request.url.path == '/auth/login') return jsonResponse(leaseJson());
        if (request.url.path == '/auth/me') return me.future;
        revoked = true;
        return jsonResponse(null, status: 204);
      });
      final attempt = controller.signIn('fictional', 'password');
      await Future<void>.delayed(Duration.zero);
      controller.cancelSignIn();
      await Future<void>.delayed(Duration.zero);
      try {
        expect(revoked, true);
      } finally {
        me.complete(jsonResponse(userJson()));
        await attempt;
        controller.dispose();
      }
    },
  );

  test(
    'unsupported role on resume clears and revokes the current lease',
    () async {
      var meCalls = 0;
      var revoked = false;
      final controller = session((request) {
        if (request.url.path == '/auth/login') return jsonResponse(leaseJson());
        if (request.url.path == '/auth/me') {
          return jsonResponse(
            userJson(role: meCalls++ == 0 ? 'AUDITOR' : 'VIEWER'),
          );
        }
        revoked = true;
        return jsonResponse(null, status: 204);
      });
      await controller.signIn('fictional', 'password');
      await controller.verifyOnResume();
      expect(controller.user, isNull);
      expect(revoked, true);
      controller.dispose();
    },
  );
}
