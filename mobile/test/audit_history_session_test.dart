import 'dart:async';
import 'dart:convert';

import 'package:bhli_audit/core/network/api_client.dart';
import 'package:bhli_audit/core/network/api_failure.dart';
import 'package:bhli_audit/core/network/api_origin.dart';
import 'package:bhli_audit/features/audits/audit_history_controller.dart';
import 'package:bhli_audit/features/audits/audit_list_controller.dart';
import 'package:bhli_audit/features/audits/models.dart';
import 'package:bhli_audit/features/auth/session_controller.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'network_test_support.dart';
import 'audit_history_contract_test.dart' show historyEvent;
import 'audit_history_archive_test.dart' show historyPage;

Future<SessionController> liveSession(
  FutureOr<http.StreamedResponse> Function(http.BaseRequest) read, {
  String Function()? role,
  int Function()? identityId,
}) async {
  final session = SessionController(
    (origin) => ApiClient(
      origin,
      clientFactory: () => RecordingClient((r) {
        if (r.url.path == '/auth/login') return jsonResponse(leaseJson());
        if (r.url.path == '/auth/me') {
          return jsonResponse({
            ...userJson(role: role?.call() ?? 'AUDITOR'),
            'id': identityId?.call() ?? 8,
          });
        }
        if (r.url.path == '/auth/logout') {
          return jsonResponse(null, status: 204);
        }
        return read(r);
      }),
    ),
    clock: () => DateTime.utc(2026, 10, 28, 12),
  )..setOrigin(ApiOrigin.parse('https://example.com'));
  await session.signIn('fictional', 'password');
  addTearDown(session.dispose);
  return session;
}

void main() {
  test(
    'archived history cannot publish after same-generation role downgrade',
    () async {
      var role = 'ADMIN';
      final response = Completer<http.StreamedResponse>();
      final session = await liveSession(
        (r) => response.future,
        role: () => role,
      );
      final generation = session.generation;
      final rejected = expectLater(
        session.fetchAuditHistory(1, includeDeleted: true),
        throwsA(isA<ApiFailure>()),
      );
      await Future<void>.delayed(Duration.zero);
      role = 'AUDITOR';
      await session.verifyOnResume();
      expect(session.generation, generation);
      response.complete(
        jsonResponse(historyPage(events: [historyEvent(action: 'DELETE')])),
      );
      await rejected;
    },
  );
  for (final role in ['ADMIN', 'AUDITOR']) {
    test(
      '$role active history uses 10 oldest events and no archived transport',
      () async {
        final requests = <http.BaseRequest>[];
        final session = await liveSession((r) {
          requests.add(r);
          return jsonResponse(
            historyPage(
              events: [
                historyEvent(id: 1),
                historyEvent(id: 2, action: 'UPDATE'),
              ],
              total: 2,
            ),
          );
        }, role: () => role);
        // Match truthful metadata for two events.
        final result = await session.fetchAuditHistory(1);
        expect(result.items.map((e) => e.id), [1, 2]);
        expect(requests.single.url.queryParameters, {
          'page': '1',
          'page_size': '10',
        });
      },
    );
  }
  test(
    'AUDITOR archived list detail and history are rejected before transport',
    () async {
      var calls = 0;
      final session = await liveSession((r) {
        calls++;
        return jsonResponse({});
      });
      await expectLater(
        session.fetchAudits(AuditQuery(), includeDeleted: true),
        throwsA(isA<ApiFailure>()),
      );
      await expectLater(
        session.fetchAudit(1, includeDeleted: true),
        throwsA(isA<ApiFailure>()),
      );
      await expectLater(
        session.fetchAuditHistory(1, includeDeleted: true),
        throwsA(isA<ApiFailure>()),
      );
      expect(calls, 0);
    },
  );
  test(
    'ADMIN active-only reads reject unexpected archived snapshots',
    () async {
      final archived = {
        ...auditJson(),
        'deleted_at': '2026-10-28T12:00:00Z',
        'deleted_by_user_id': 8,
      };
      final session = await liveSession(
        (r) => jsonResponse(
          r.url.path.endsWith('/history')
              ? historyPage(events: [historyEvent(action: 'DELETE')])
              : r.url.path == '/audits'
              ? {
                  'items': [archived],
                  'total': 1,
                  'page': 1,
                  'page_size': 25,
                }
              : archived,
          headers: {'etag': '"3"'},
        ),
        role: () => 'ADMIN',
      );
      await expectLater(
        session.fetchAudits(AuditQuery()),
        throwsA(isA<ApiFailure>()),
      );
      await expectLater(session.fetchAudit(1), throwsA(isA<ApiFailure>()));
      await expectLater(
        session.fetchAuditHistory(1),
        throwsA(isA<ApiFailure>()),
      );
    },
  );
  test('history rejects an oversized streamed body without returning partial events', () async {
    final session = await liveSession(
      (r) => http.StreamedResponse(
        Stream.fromIterable([
          utf8.encode('{"items":['),
          List.filled(2 * 1024 * 1024, 32),
        ]),
        200,
        headers: {'content-type': 'application/json'},
      ),
    );
    await expectLater(
      session.fetchAuditHistory(1),
      throwsA(
        isA<ApiFailure>().having((e) => e.code, 'safe failure', 'protocol'),
      ),
    );
  });
  test(
    'history controller erases snapshots and ignores late results on logout',
    () async {
      final delayed = Completer<http.StreamedResponse>();
      var calls = 0;
      final session = await liveSession(
        (r) => ++calls == 1 ? jsonResponse(historyPage()) : delayed.future,
      );
      final controller = AuditHistoryController(session, 1);
      addTearDown(controller.dispose);
      await controller.refresh();
      expect(controller.page!.items.single.id, 1);
      final pending = controller.refresh();
      await Future<void>.delayed(Duration.zero);
      await session.signOut();
      expect(controller.page, isNull);
      expect(controller.unavailable, true);
      delayed.complete(jsonResponse(historyPage()));
      await pending;
      expect(controller.page, isNull);
    },
  );
  test('history newer refresh supersedes old page response', () async {
    final delayed = Completer<http.StreamedResponse>();
    var calls = 0;
    final session = await liveSession(
      (r) => ++calls == 1
          ? delayed.future
          : jsonResponse(historyPage(events: [historyEvent(id: 2)])),
    );
    final controller = AuditHistoryController(session, 1);
    addTearDown(controller.dispose);
    final first = controller.refresh();
    await Future<void>.delayed(Duration.zero);
    await controller.refresh();
    delayed.complete(jsonResponse(historyPage()));
    await first;
    expect(controller.page!.items.single.id, 2);
  });
  test(
    'archive list mode preserves filters page25 and is erased on role loss',
    () async {
      var role = 'ADMIN';
      final queries = <Map<String, String>>[];
      final session = await liveSession((r) {
        queries.add(r.url.queryParameters);
        return jsonResponse({
          'items': [
            {
              ...auditJson(),
              'deleted_at': '2026-10-28T12:00:00Z',
              'deleted_by_user_id': 8,
            },
          ],
          'total': 26,
          'page': int.parse(r.url.queryParameters['page']!),
          'page_size': 25,
        });
      }, role: () => role);
      final controller = AuditListController(session);
      addTearDown(controller.dispose);
      await controller.apply(
        AuditQuery(driverName: 'Fictional', sort: 'audit_date'),
      );
      await controller.setIncludeArchived(true);
      await controller.next();
      expect(controller.page!.items.single.deletedAt, isNotNull);
      expect(queries.last, containsPair('page', '2'));
      expect(queries.last, containsPair('driver_name', 'Fictional'));
      expect(queries.last, containsPair('page_size', '25'));
      expect(queries.last, containsPair('include_deleted', 'true'));
      role = 'AUDITOR';
      await session.verifyOnResume();
      expect(controller.page, isNull);
      expect(controller.includeArchived, false);
    },
  );
  test(
    'history response cannot cross an identity ID change during resume',
    () async {
      var id = 8;
      final response = Completer<http.StreamedResponse>();
      final session = await liveSession(
        (r) => response.future,
        identityId: () => id,
      );
      final rejected = expectLater(
        session.fetchAuditHistory(1),
        throwsA(isA<ApiFailure>()),
      );
      await Future<void>.delayed(Duration.zero);
      id = 19;
      await session.verifyOnResume();
      response.complete(jsonResponse(historyPage()));
      await rejected;
    },
  );
  for (final operation in ['list', 'detail', 'history']) {
    test(
      '$operation archived dispatch rechecks role after awaited resume',
      () async {
        var role = 'ADMIN';
        var calls = 0;
        final session = await liveSession((r) {
          calls++;
          return jsonResponse({});
        }, role: () => role);
        final request = switch (operation) {
          'list' => session.fetchAudits(AuditQuery(), includeDeleted: true),
          'detail' => session.fetchAudit(1, includeDeleted: true),
          _ => session.fetchAuditHistory(1, includeDeleted: true),
        };
        final rejected = expectLater(request, throwsA(isA<ApiFailure>()));
        role = 'AUDITOR';
        await session.verifyOnResume();
        await rejected;
        expect(calls, 0);
      },
    );
  }
  test(
    'archived history state clears immediately on role loss and stays cleared',
    () async {
      var role = 'ADMIN';
      final delayed = Completer<http.StreamedResponse>();
      var calls = 0;
      final session = await liveSession(
        (r) => ++calls == 1
            ? jsonResponse(
                historyPage(events: [historyEvent(action: 'DELETE')]),
              )
            : delayed.future,
        role: () => role,
      );
      final controller = AuditHistoryController(
        session,
        1,
        includeArchived: true,
      );
      addTearDown(controller.dispose);
      await controller.refresh();
      expect(controller.page!.items.single.after.archived, true);
      final pending = controller.refresh();
      await Future<void>.delayed(Duration.zero);
      role = 'AUDITOR';
      await session.verifyOnResume();
      expect(controller.page, isNull);
      expect(controller.unavailable, true);
      delayed.complete(
        jsonResponse(historyPage(events: [historyEvent(action: 'DELETE')])),
      );
      await pending;
      expect(controller.page, isNull);
    },
  );
  for (final status in [403, 404]) {
    test('history $status clears data and disables subsequent reads', () async {
      var calls = 0;
      final session = await liveSession(
        (r) => ++calls == 1
            ? jsonResponse(historyPage())
            : jsonResponse({}, status: status),
      );
      final controller = AuditHistoryController(session, 1);
      addTearDown(controller.dispose);
      await controller.refresh();
      await controller.refresh();
      expect(controller.page, isNull);
      expect(controller.unavailable, true);
      expect(controller.error, isNotNull);
      await controller.refresh();
      expect(calls, 2);
    });
  }
}
