import 'dart:async';

import 'package:bhli_audit/core/network/api_client.dart';
import 'package:bhli_audit/core/network/api_origin.dart';
import 'package:bhli_audit/features/audits/audit_list_controller.dart';
import 'package:bhli_audit/features/audits/models.dart';
import 'package:bhli_audit/features/auth/session_controller.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'network_test_support.dart';

// A controlled read adapter isolates request ordering from the separately tested
// bearer lifecycle. Integration tests below also exercise the real session.
class DeferredReadSession extends SessionController {
  DeferredReadSession(this.read)
    : super((_) => throw StateError('No transport'));
  final Future<AuditPage> Function(AuditQuery) read;
  @override
  int generation = 1;
  @override
  Future<AuditPage> fetchAudits(
    AuditQuery query, {
    bool includeDeleted = false,
  }) => read(query);
  @override
  Future<void> signOut() async {
    generation++;
    notifyListeners();
  }
}

void main() {
  test('superseded read completion cannot replace current page', () async {
    final old = Completer<AuditPage>();
    final current = AuditPage.fromJson({
      'items': [auditJson(id: 2)],
      'total': 1,
      'page': 1,
      'page_size': 25,
    }, AuditQuery());
    final session = DeferredReadSession(
      (query) => query.driverName == 'old' ? old.future : Future.value(current),
    );
    final list = AuditListController(session);
    addTearDown(list.dispose);
    addTearDown(session.dispose);
    final first = list.apply(AuditQuery(driverName: 'old'));
    await list.apply(AuditQuery(station: 'new'));
    old.complete(
      AuditPage.fromJson({
        'items': [auditJson()],
        'total': 1,
        'page': 1,
        'page_size': 25,
      }, AuditQuery()),
    );
    await first;
    expect(list.page?.items.single.id, 2);
    await session.signOut();
    expect(list.page, isNull);
  });

  Future<SessionController> signedIn(
    FutureOr<http.StreamedResponse> Function(http.BaseRequest) read,
  ) async {
    final session = SessionController(
      (origin) => ApiClient(
        origin,
        clientFactory: () => RecordingClient((r) {
          if (r.url.path == '/auth/login') return jsonResponse(leaseJson());
          if (r.url.path == '/auth/me') return jsonResponse(userJson());
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

  Object page(int id, {int number = 1}) => {
    'items': [auditJson(id: id)],
    'total': 26,
    'page': number,
    'page_size': 25,
  };

  test('an older search cannot overwrite the newest results', () async {
    final old = Completer<http.StreamedResponse>();
    final session = await signedIn(
      (r) => r.url.queryParameters['driver_name'] == 'old'
          ? old.future
          : jsonResponse(page(2)),
    );
    final list = AuditListController(session);
    addTearDown(list.dispose);
    final first = list.apply(AuditQuery(driverName: 'old'));
    await Future<void>.delayed(Duration.zero);
    await list.apply(AuditQuery(station: 'new'));
    old.complete(jsonResponse(page(1)));
    await first;
    expect(list.page!.items.single.id, 2);
    expect(list.query.station, 'new');
  });

  test(
    'paging preserves filters and visible refresh returns to page one',
    () async {
      final queries = <Map<String, String>>[];
      final session = await signedIn((r) {
        queries.add(r.url.queryParameters);
        return jsonResponse(
          page(1, number: int.parse(r.url.queryParameters['page']!)),
        );
      });
      final list = AuditListController(session);
      addTearDown(list.dispose);
      await list.apply(AuditQuery(plateNumber: '000123', sort: 'audit_date'));
      await list.next();
      expect(list.query.page, 2);
      await list.refresh();
      expect(list.query.page, 1);
      expect(queries[1]['plate_number'], '000123');
      expect(queries[1]['sort'], 'audit_date');
      expect(queries[2]['page'], '1');
    },
  );

  test(
    'failed next page cannot relabel old rows or skip the failed page',
    () async {
      final requests = <int>[];
      final session = await signedIn((request) {
        final number = int.parse(request.url.queryParameters['page']!);
        requests.add(number);
        return number == 2
            ? jsonResponse({}, status: 503)
            : jsonResponse(page(1));
      });
      final list = AuditListController(session);
      addTearDown(list.dispose);
      await list.refresh();
      await list.next();
      expect(list.page, isNull);
      expect(list.query.page, 2);
      expect(list.error, isNotNull);
      await list.next();
      expect(requests, [1, 2]);
    },
  );

  test(
    'failed refresh marks retained records stale and sign out erases them',
    () async {
      var offline = false;
      final session = await signedIn(
        (r) => offline
            ? jsonResponse({
                'error': {'code': 'unavailable'},
              }, status: 503)
            : jsonResponse(page(1)),
      );
      final list = AuditListController(session);
      addTearDown(list.dispose);
      await list.refresh();
      offline = true;
      await list.refresh();
      expect(list.page!.items.single.id, 1);
      expect(list.error, isNotNull);
      expect(list.stale, true);
      await session.signOut();
      expect(list.page, isNull);
      expect(list.error, isNull);
    },
  );
}
