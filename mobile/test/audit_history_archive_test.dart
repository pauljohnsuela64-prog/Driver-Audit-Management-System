import 'dart:async';

import 'package:bhli_audit/core/network/api_client.dart';
import 'package:bhli_audit/core/network/api_origin.dart';
import 'package:bhli_audit/features/audits/audit_details_screen.dart';
import 'package:bhli_audit/features/audits/audit_list_screen.dart';
import 'package:bhli_audit/features/audits/audit_history_screen.dart';
import 'package:bhli_audit/ui/core/audit_theme.dart';
import 'package:bhli_audit/features/auth/session_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'network_test_support.dart';
import 'audit_history_contract_test.dart' show historyEvent;

Future<SessionController> historySession(
  FutureOr<http.StreamedResponse> Function(http.BaseRequest) read, {
  String role = 'AUDITOR',
  String Function()? currentRole,
}) async {
  final session = SessionController(
    (origin) => ApiClient(
      origin,
      clientFactory: () => RecordingClient((r) {
        if (r.url.path == '/auth/login') return jsonResponse(leaseJson());
        if (r.url.path == '/auth/me') {
          return jsonResponse(userJson(role: currentRole?.call() ?? role));
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
  return session;
}

Object historyPage({List<Object?>? events, int page = 1, int total = 1}) => {
  'items': events ?? [historyEvent()],
  'page': page,
  'page_size': 10,
  'total': total,
};
void main() {
  testWidgets('active detail offers dedicated history with account ID author', (
    tester,
  ) async {
    final session = await historySession(
      (r) => r.url.path.endsWith('/history')
          ? jsonResponse(historyPage())
          : jsonResponse(auditJson(), headers: {'etag': '"3"'}),
    );
    addTearDown(session.dispose);
    await tester.pumpWidget(
      MaterialApp(home: AuditDetailsScreen(session: session, auditId: 1)),
    );
    await tester.pumpAndSettle();
    expect(find.text('History'), findsOneWidget);
    await tester.tap(find.text('History'));
    await tester.pumpAndSettle();
    expect(find.text('Audit history'), findsOneWidget);
    expect(find.text('Changed by User #9'), findsOneWidget);
    expect(find.text('Created'), findsOneWidget);
  });
  testWidgets('ADMIN explicitly includes active and archived records', (
    tester,
  ) async {
    final queries = <Map<String, String>>[];
    final session = await historySession((r) {
      queries.add(r.url.queryParameters);
      return jsonResponse({
        'items': [
          auditJson(),
          if (r.url.queryParameters['include_deleted'] == 'true')
            {
              ...auditJson(id: 2),
              'deleted_at': '2026-10-28T12:00:00Z',
              'deleted_by_user_id': 8,
            },
        ],
        'total': r.url.queryParameters['include_deleted'] == 'true' ? 2 : 1,
        'page': 1,
        'page_size': 25,
      });
    }, role: 'ADMIN');
    addTearDown(session.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: AuditListScreen(session: session, onSettings: () {}),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Include archived'), findsOneWidget);
    expect(queries.single.containsKey('include_deleted'), false);
    await tester.tap(find.text('Include archived'));
    await tester.pumpAndSettle();
    expect(queries.last['include_deleted'], 'true');
    expect(queries.last['page_size'], '25');
    await tester.scrollUntilVisible(
      find.text('Archived \u00b7 Read-only'),
      300,
      scrollable: find
          .descendant(
            of: find.byType(CustomScrollView),
            matching: find.byType(Scrollable),
          )
          .first,
    );
    expect(find.text('Archived · Read-only'), findsOneWidget);
  });
  testWidgets(
    'AUDITOR never sees archive browsing and active history is read only',
    (tester) async {
      final requests = <http.BaseRequest>[];
      final session = await historySession((r) {
        requests.add(r);
        return jsonResponse({
          'items': [],
          'total': 0,
          'page': 1,
          'page_size': 25,
        });
      });
      addTearDown(session.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: AuditListScreen(session: session, onSettings: () {}),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Include archived'), findsNothing);
      expect(
        requests.every(
          (r) => !r.url.queryParameters.containsKey('include_deleted'),
        ),
        true,
      );
    },
  );
  for (final brightness in Brightness.values) {
    testWidgets(
      'history wraps maximum Unicode values at 320dp 200% $brightness',
      (tester) async {
        tester.view.physicalSize = const Size(320, 700);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        final event = historyEvent(action: 'UPDATE');
        (event['after_data'] as Map)['remarks'] =
            ('\u9053\u8def\u{1f69a}' * 3333 + 'X');
        (event['after_data'] as Map)['password_hash'] = 'PRIVATE_METADATA';
        (event['before_data'] as Map)['remarks'] = null;
        final session = await historySession(
          (r) => jsonResponse(historyPage(events: [event])),
        );
        addTearDown(session.dispose);
        await tester.pumpWidget(
          MaterialApp(
            theme: auditTheme(Brightness.light),
            darkTheme: auditTheme(Brightness.dark),
            themeMode: brightness == Brightness.dark
                ? ThemeMode.dark
                : ThemeMode.light,
            builder: (context, child) => MediaQuery(
              data: MediaQuery.of(context)
                  .copyWith(textScaler: TextScaler.linear(2)),
              child: child!,
            ),
            home: AuditHistoryScreen(session: session, auditId: 1),
          ),
        );
        await tester.pumpAndSettle();
        await tester.scrollUntilVisible(
          find.text('View changes and UTC time'),
          250,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.ensureVisible(find.text('View changes and UTC time'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('View changes and UTC time'));
        await tester.pumpAndSettle();
        await tester.scrollUntilVisible(
          find.text('Previous value'),
          250,
          scrollable: find.byType(Scrollable).first,
        );
        expect(find.text('Not provided'), findsOneWidget);
        expect(find.text('Updated value'), findsOneWidget);
        expect(
          find.text(('\u9053\u8def\u{1f69a}' * 3333 + 'X')),
          findsOneWidget,
        );
        expect(find.textContaining('PRIVATE_METADATA'), findsNothing);
        expect(find.textContaining('UTC:'), findsOneWidget);
        expect(tester.takeException(), isNull);
      },
    );
  }
  testWidgets(
    'history supports loading error retry empty refresh and oldest-first paging',
    (tester) async {
      final pending = Completer<http.StreamedResponse>();
      final pages = <int>[];
      var failure = true;
      final session = await historySession((r) {
        final number = int.parse(r.url.queryParameters['page']!);
        pages.add(number);
        if (pages.length == 1) return pending.future;
        if (failure) return jsonResponse({}, status: 503);
        if (number == 2) {
          return jsonResponse(historyPage(events: [], page: 2, total: 11));
        }
        return jsonResponse(
          historyPage(
            events: [
              historyEvent(id: 1),
              historyEvent(id: 2, action: 'UPDATE'),
            ],
            total: 11,
          ),
        );
      });
      addTearDown(session.dispose);
      await tester.pumpWidget(
        MaterialApp(home: AuditHistoryScreen(session: session, auditId: 1)),
      );
      await tester.pump();
      expect(find.byType(LinearProgressIndicator), findsOneWidget);
      pending.complete(jsonResponse({}, status: 503));
      await tester.pumpAndSettle();
      expect(find.text('Retry'), findsOneWidget);
      failure = false;
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.text('Created'), findsOneWidget);
      expect(find.text('Updated'), findsOneWidget);
      expect(
        tester.getTopLeft(find.text('Created')).dy,
        lessThan(tester.getTopLeft(find.text('Updated')).dy),
      );
      await tester.scrollUntilVisible(
        find.text('Next'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Next'));
      await tester.pumpAndSettle();
      expect(find.text('No history events available.'), findsOneWidget);
      await tester.scrollUntilVisible(
        find.text('Previous'),
        -300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Previous'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Refresh'),
        -300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Refresh'));
      await tester.pumpAndSettle();
      expect(pages, [1, 1, 2, 1, 1]);
    },
  );

  testWidgets('direct archived history denied to AUDITOR shows unavailable', (
    tester,
  ) async {
    var calls = 0;
    final session = await historySession((r) {
      calls++;
      return jsonResponse(historyPage());
    });
    addTearDown(session.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: AuditHistoryScreen(
          session: session,
          auditId: 1,
          includeArchived: true,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('This audit history is unavailable.'), findsOneWidget);
    expect(calls, 0);
  });

  testWidgets(
    'archived ADMIN detail stays read only and opens archived history then Back',
    (tester) async {
      final requests = <http.BaseRequest>[];
      final session = await historySession((r) {
        requests.add(r);
        if (r.url.path.endsWith('/history')) {
          return jsonResponse(
            historyPage(events: [historyEvent(action: 'DELETE')]),
          );
        }
        return jsonResponse(
          {
            ...auditJson(),
            'deleted_at': '2026-10-28T12:00:00Z',
            'deleted_by_user_id': 8,
          },
          headers: {'etag': '"3"'},
        );
      }, role: 'ADMIN');
      addTearDown(session.dispose);
      await tester.pumpWidget(
        MaterialApp(
          theme: auditTheme(Brightness.light),
          home: AuditDetailsScreen(
            session: session,
            auditId: 1,
            includeArchived: true,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Archived \u00b7 Read-only'), findsOneWidget);
      expect(find.byIcon(Icons.archive_outlined), findsOneWidget);
      expect(find.text('Edit'), findsNothing);
      expect(find.text('Archive audit'), findsNothing);
      final history = find.widgetWithText(OutlinedButton, 'History');
      expect(tester.getSize(history).height, greaterThanOrEqualTo(48));
      await tester.tap(history);
      await tester.pumpAndSettle();
      expect(find.text('Archived'), findsOneWidget);
      await tester.tap(find.text('View changes and UTC time'));
      await tester.pumpAndSettle();
      expect(find.text('Status'), findsOneWidget);
      expect(find.text('Active'), findsOneWidget);
      expect(
        requests.every(
          (r) =>
              r.method == 'GET' &&
              r.url.queryParameters['include_deleted'] == 'true',
        ),
        true,
      );
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.text('Audit details'), findsOneWidget);
    },
  );
  for (final size in [const Size(640, 320), const Size(1024, 768)]) {
    testWidgets('history 300 percent text supports landscape or tablet $size', (
      tester,
    ) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final event = historyEvent();
      event['actor_user_id'] = 8;
      final session = await historySession(
        (r) => jsonResponse(historyPage(events: [event])),
      );
      addTearDown(session.dispose);
      await tester.pumpWidget(
        MaterialApp(
          theme: auditTheme(Brightness.dark),
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context)
                .copyWith(textScaler: TextScaler.linear(3)),
            child: child!,
          ),
          home: AuditHistoryScreen(session: session, auditId: 1),
        ),
      );
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Changed by you \u00b7 User #8'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('Changed by you \u00b7 User #8'), findsOneWidget);
      await tester.scrollUntilVisible(
        find.text('View changes and UTC time'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.ensureVisible(find.text('View changes and UTC time'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('View changes and UTC time'));
      await tester.pumpAndSettle();
      expect(find.text('Not provided'), findsOneWidget);
      await tester.scrollUntilVisible(
        find.text('Next'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.widgetWithText(OutlinedButton, 'Next'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }
  testWidgets(
    'Include archived visibility follows same-generation role changes while off',
    (tester) async {
      var role = 'ADMIN';
      final session = await historySession(
        (r) =>
            jsonResponse({'items': [], 'total': 0, 'page': 1, 'page_size': 25}),
        currentRole: () => role,
      );
      addTearDown(session.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: AuditListScreen(session: session, onSettings: () {}),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Include archived'), findsOneWidget);
      final generation = session.generation;
      role = 'AUDITOR';
      await session.verifyOnResume();
      await tester.pumpAndSettle();
      expect(session.generation, generation);
      expect(find.text('Include archived'), findsNothing);
      role = 'ADMIN';
      await session.verifyOnResume();
      await tester.pumpAndSettle();
      expect(find.text('Include archived'), findsOneWidget);
    },
  );
}
