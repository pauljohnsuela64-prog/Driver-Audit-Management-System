import 'dart:convert';

import 'package:bhli_audit/core/network/api_client.dart';
import 'package:bhli_audit/core/network/api_origin.dart';
import 'package:bhli_audit/features/auth/session_controller.dart';
import 'package:bhli_audit/features/audits/audit_list_screen.dart';
import 'package:bhli_audit/features/audits/audit_details_screen.dart';
import 'package:bhli_audit/ui/core/audit_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'network_test_support.dart';

void main() {
  late SessionController session;
  late List<http.BaseRequest> requests;
  var role = 'ADMIN';
  var id = 8;
  var detailCalls = 0;
  Future<http.StreamedResponse> Function(http.BaseRequest)? override;
  Future<void> setup() async {
    requests = [];
    detailCalls = 0;
    override = null;
    session = SessionController(
      (origin) => ApiClient(
        origin,
        clientFactory: () => RecordingClient((r) {
          requests.add(r);
          if (r.url.path == '/auth/login') return jsonResponse(leaseJson());
          if (r.url.path == '/auth/me') {
            return jsonResponse({...userJson(role: role), 'id': id});
          }
          if (r.url.path == '/auth/logout') {
            return http.StreamedResponse(const Stream.empty(), 204);
          }
          if (override != null) return override!(r);
          if (r.url.path == '/audits') {
            return jsonResponse({
              'items': [auditJson()],
              'total': 26,
              'page': int.parse(r.url.queryParameters['page']!),
              'page_size': 25,
            });
          }
          detailCalls++;
          return jsonResponse(auditJson(), headers: {'etag': '"3"'});
        }),
      ),
      clock: () => DateTime.utc(2026, 10, 28, 12),
    )..setOrigin(ApiOrigin.parse('https://example.com'));
    await session.signIn('fictional', 'password');
  }

  tearDown(() => session.dispose());
  Future<void> enter(WidgetTester tester, String label, String value) async {
    final field = find.widgetWithText(TextFormField, label);
    await tester.ensureVisible(field);
    await tester.enterText(field, value);
  }

  Future<void> saveCreate(WidgetTester tester) async {
    await enter(tester, 'Driver Name', 'Fictional José 李');
    await enter(tester, 'Audit Date', '2026-10-28');
    await enter(tester, 'Station', 'South');
    await enter(tester, 'Plate Number', '000123');
    final save = find.widgetWithText(FilledButton, 'Save');
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.ensureVisible(save);
    await tester.pumpAndSettle();
    await tester.tap(save);
    await tester.pumpAndSettle();
  }

  testWidgets('New Audit action opens the six-field form', (tester) async {
    role = 'ADMIN';
    id = 8;
    await setup();
    await tester.pumpWidget(
      MaterialApp(
        theme: auditTheme(Brightness.light),
        home: AuditListScreen(session: session, onSettings: () {}),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('New Audit'), findsOneWidget);
    await tester.tap(find.text('New Audit'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextFormField, 'Driver Name'), findsOneWidget);
    expect(find.widgetWithText(TextFormField, 'Audit Date'), findsOneWidget);
    expect(find.textContaining('server'), findsWidgets);
  });
  for (final scenario in [
    ('ADMIN', 9, true),
    ('AUDITOR', 8, true),
    ('AUDITOR', 9, false),
  ]) {
    testWidgets(
      '${scenario.$1} ID${scenario.$2} Edit visibility follows stable owner ID',
      (tester) async {
        role = scenario.$1;
        id = scenario.$2;
        await setup();
        await tester.pumpWidget(
          MaterialApp(home: AuditDetailsScreen(session: session, auditId: 1)),
        );
        await tester.pumpAndSettle();
        expect(find.text('Edit'), scenario.$3 ? findsOneWidget : findsNothing);
      },
    );
  }
  testWidgets('Edit refetches current ETag and sends only changed fields', (
    tester,
  ) async {
    role = 'ADMIN';
    id = 8;
    await setup();
    override = (r) async {
      if (r.method == 'PATCH') {
        return jsonResponse(
          {...auditJson(), 'version': 5, 'helper_name': 'New helper'},
          headers: {'etag': '"5"'},
        );
      }
      detailCalls++;
      final v = detailCalls == 1
          ? 3
          : detailCalls == 2
          ? 4
          : 5;
      return jsonResponse(
        {...auditJson(), 'version': v, if (v == 5) 'helper_name': 'New helper'},
        headers: {'etag': '"$v"'},
      );
    };
    await tester.pumpWidget(
      MaterialApp(
        theme: auditTheme(Brightness.light),
        home: AuditDetailsScreen(session: session, auditId: 1),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Edit'));
    await tester.pumpAndSettle();
    expect(detailCalls, 2);
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Helper Name (optional)'),
      'New helper',
    );
    final save = find.widgetWithText(FilledButton, 'Save');
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.ensureVisible(save);
    await tester.pumpAndSettle();
    await tester.tap(save);
    await tester.pumpAndSettle();
    final patch =
        requests.singleWhere((r) => r.method == 'PATCH') as http.Request;
    expect(patch.headers['if-match'], '"4"');
    expect(jsonDecode(patch.body), {'helper_name': 'New helper'});
    expect(find.text('Audit details'), findsOneWidget);
    expect(find.textContaining('saved'), findsWidgets);
  });
  testWidgets(
    'confirmed create preserves filters and sort, returns page1 and explains filtered visibility',
    (tester) async {
      role = 'ADMIN';
      id = 8;
      await setup();
      Map<String, Object?>? saved;
      override = (r) async {
        if (r.method == 'POST') {
          saved = {
            ...auditJson(id: 2),
            ...(jsonDecode((r as http.Request).body) as Map<String, dynamic>),
            'version': 1,
          };
          return jsonResponse(saved, status: 201, headers: {'etag': '"1"'});
        }
        if (r.url.path == '/audits') {
          return jsonResponse({
            'items': [auditJson()],
            'total': 26,
            'page': int.parse(r.url.queryParameters['page']!),
            'page_size': 25,
          });
        }
        return jsonResponse(saved, headers: {'etag': '"1"'});
      };
      await tester.pumpWidget(
        MaterialApp(
          theme: auditTheme(Brightness.light),
          home: AuditListScreen(session: session, onSettings: () {}),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Driver name'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Station').last);
      await tester.pumpAndSettle();
      await enter(tester, 'Search audits', 'North');
      await tester.tap(find.widgetWithText(FilledButton, 'Search'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Newest created'));
      await tester.tap(find.text('Newest created'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Oldest audit date').last);
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Next'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Next'));
      await tester.pumpAndSettle();
      expect(requests.last.url.queryParameters['page'], '2');
      await tester.ensureVisible(find.text('New Audit'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('New Audit'));
      await tester.pumpAndSettle();
      await saveCreate(tester);
      final list = requests
          .where((r) => r.method == 'GET' && r.url.path == '/audits')
          .last;
      expect(list.url.queryParameters['page'], '1');
      expect(list.url.queryParameters['station'], 'North');
      expect(list.url.queryParameters['sort'], 'audit_date');
      expect(find.textContaining('may not appear'), findsOneWidget);
      expect(find.text('Audit details'), findsOneWidget);
    },
  );
  testWidgets(
    'confirmed create remains saved when list and detail refresh fail',
    (tester) async {
      role = 'ADMIN';
      id = 8;
      await setup();
      var saved = false;
      override = (r) async {
        if (r.method == 'POST') {
          saved = true;
          return jsonResponse(
            {
              ...auditJson(id: 2),
              ...(jsonDecode((r as http.Request).body) as Map<String, dynamic>),
              'version': 1,
            },
            status: 201,
            headers: {'etag': '"1"'},
          );
        }
        if (saved) return jsonResponse({}, status: 503);
        return jsonResponse({
          'items': [auditJson()],
          'total': 1,
          'page': 1,
          'page_size': 25,
        });
      };
      await tester.pumpWidget(
        MaterialApp(
          theme: auditTheme(Brightness.light),
          home: AuditListScreen(session: session, onSettings: () {}),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('New Audit'));
      await tester.pumpAndSettle();
      await saveCreate(tester);
      expect(find.text('Audit saved.'), findsOneWidget);
      expect(find.text('Fictional José 李'), findsOneWidget);
      expect(
        requests
            .where((r) => r.method == 'POST' && r.url.path == '/audits')
            .length,
        1,
      );
      await tester.pageBack();
      await tester.pumpAndSettle();
      expect(find.text('Audit saved.'), findsOneWidget);
      await tester.scrollUntilVisible(
        find.textContaining('service is unavailable'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.textContaining('service is unavailable'), findsOneWidget);
    },
  );
  testWidgets('fresh authorization failure prevents opening Edit', (
    tester,
  ) async {
    role = 'ADMIN';
    id = 8;
    await setup();
    override = (r) async {
      detailCalls++;
      return detailCalls == 1
          ? jsonResponse(auditJson(), headers: {'etag': '"3"'})
          : jsonResponse({}, status: 403);
    };
    await tester.pumpWidget(
      MaterialApp(home: AuditDetailsScreen(session: session, auditId: 1)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Edit'));
    await tester.pumpAndSettle();
    expect(find.text('Edit Audit'), findsNothing);
    expect(find.text('Edit'), findsNothing);
    expect(requests.where((r) => r.method == 'PATCH'), isEmpty);
  });
  testWidgets('double New Audit does not stack duplicate forms', (
    tester,
  ) async {
    role = 'ADMIN';
    id = 8;
    await setup();
    await tester.pumpWidget(
      MaterialApp(
        home: AuditListScreen(session: session, onSettings: () {}),
      ),
    );
    await tester.pumpAndSettle();
    final action = tester
        .widget<FilledButton>(find.widgetWithText(FilledButton, 'New Audit'))
        .onPressed!;
    action();
    action();
    await tester.pumpAndSettle();
    final cancel = find.widgetWithText(TextButton, 'Cancel');
    await tester.ensureVisible(cancel);
    await tester.tap(cancel);
    await tester.pumpAndSettle();
    expect(find.text('Driver Audits'), findsOneWidget);
  });
  testWidgets(
    'conflict reopening needs explicit fresh baseline and never resubmits old draft',
    (tester) async {
      role = 'ADMIN';
      id = 8;
      await setup();
      var writes = 0;
      override = (r) async {
        if (r.method == 'PATCH') {
          writes++;
          if (writes == 1) return jsonResponse({}, status: 412);
          return jsonResponse(
            {
              ...auditJson(),
              'version': 6,
              'helper_name': 'Other helper',
              'station': 'Revised',
            },
            headers: {'etag': '"6"'},
          );
        }
        detailCalls++;
        final version = detailCalls == 1
            ? 3
            : detailCalls == 2
            ? 4
            : writes < 2
            ? 5
            : 6;
        return jsonResponse(
          {
            ...auditJson(),
            'version': version,
            if (version >= 5) 'helper_name': 'Other helper',
          },
          headers: {'etag': '"$version"'},
        );
      };
      await tester.pumpWidget(
        MaterialApp(
          theme: auditTheme(Brightness.light),
          home: AuditDetailsScreen(session: session, auditId: 1),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Edit'));
      await tester.pumpAndSettle();
      await enter(tester, 'Helper Name (optional)', 'My old draft');
      FocusManager.instance.primaryFocus?.unfocus();
      await tester.ensureVisible(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(
        find.widgetWithText(TextButton, 'Discard my changes'),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(TextButton, 'Discard my changes'));
      await tester.pumpAndSettle();
      await tester.tap(
        find.widgetWithText(TextButton, 'Discard my changes').last,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Edit'));
      await tester.pumpAndSettle();
      expect(writes, 1);
      final helper = tester.widget<TextFormField>(
        find.widgetWithText(TextFormField, 'Helper Name (optional)'),
      );
      expect(helper.controller!.text, 'Other helper');
      await enter(tester, 'Station', 'Revised');
      FocusManager.instance.primaryFocus?.unfocus();
      await tester.ensureVisible(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();
      final last =
          requests.where((r) => r.method == 'PATCH').last as http.Request;
      expect(last.headers['if-match'], '"5"');
      expect(jsonDecode(last.body), {'station': 'Revised'});
      expect(writes, 2);
    },
  );
  for (final status in [403, 404]) {
    testWidgets(
      'mutation$status exits editor and refreshes denied visibility',
      (tester) async {
        role = 'ADMIN';
        id = 8;
        await setup();
        var denied = false;
        var visibilityRefreshes = 0;
        override = (r) async {
          if (r.method == 'PATCH') denied = true;
          return denied
              ? jsonResponse({}, status: r.method == 'PATCH' ? status : 503)
              : jsonResponse(auditJson(), headers: {'etag': '"3"'});
        };
        await tester.pumpWidget(
          MaterialApp(
            home: AuditDetailsScreen(
              session: session,
              auditId: 1,
              onVisibilityChanged: () async {
                visibilityRefreshes++;
              },
            ),
          ),
        );
        await tester.pumpAndSettle();
        await tester.tap(find.text('Edit'));
        await tester.pumpAndSettle();
        await enter(tester, 'Station', 'Private draft');
        FocusManager.instance.primaryFocus?.unfocus();
        await tester.pumpAndSettle();
        await tester.ensureVisible(find.text('Save'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Save'));
        await tester.pumpAndSettle();
        expect(find.text('Edit Audit'), findsNothing);
        expect(find.text('Private draft'), findsNothing);
        expect(find.text('Edit'), findsNothing);
        expect(visibilityRefreshes, 1);
        expect(
          requests.where((r) => r.url.path == '/auth/me').length,
          status == 403 ? 2 : 1,
        );
        expect(tester.takeException(), isNull);
      },
    );
  }
}
