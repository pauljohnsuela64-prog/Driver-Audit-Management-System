import 'package:bhli_audit/core/network/api_failure.dart';
import 'package:bhli_audit/features/audits/audit_list_screen.dart';
import 'package:bhli_audit/features/audits/models.dart';
import 'package:bhli_audit/features/auth/session_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'network_test_support.dart';

class AuditReadSession extends SessionController {
  AuditReadSession() : super((_) => throw StateError('No transport'));
  final queries = <AuditQuery>[];
  bool missing = false;
  bool offline = false;
  bool empty = false;
  @override
  int get generation => 1;
  @override
  Future<AuditPage> fetchAudits(
    AuditQuery query, {
    bool includeDeleted = false,
  }) async {
    queries.add(query);
    if (offline) throw ApiFailure.network;
    return AuditPage.fromJson({
      'items': empty ? [] : [auditJson()],
      'total': empty ? 0 : 26,
      'page': query.page,
      'page_size': 25,
    }, query);
  }

  @override
  Future<AuditRecord> fetchAudit(int id, {bool includeDeleted = false}) async {
    if (missing) throw ApiFailure.fromStatus(404);
    return AuditRecord.fromJson(auditJson());
  }
}

void main() {
  testWidgets(
    'search selectors, sorting and paging emit exact applied queries',
    (tester) async {
      final session = AuditReadSession();
      addTearDown(session.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: AuditListScreen(session: session, onSettings: () {}),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Driver name'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Plate number').last);
      await tester.pumpAndSettle();
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Search audits'),
        '000123',
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Search'));
      await tester.pumpAndSettle();
      expect(session.queries.last.plateNumber, '000123');
      expect(session.queries.last.driverName, isNull);
      await tester.ensureVisible(find.text('Newest created'));
      await tester.tap(find.text('Newest created'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Oldest audit date').last);
      await tester.pumpAndSettle();
      expect(session.queries.last.sort, 'audit_date');
      await tester.scrollUntilVisible(
        find.widgetWithText(OutlinedButton, 'Next'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(OutlinedButton, 'Next'));
      await tester.pumpAndSettle();
      expect(session.queries.last.page, 2);
      expect(session.queries.last.plateNumber, '000123');
      await tester.tap(find.widgetWithText(OutlinedButton, 'Previous'));
      await tester.pumpAndSettle();
      expect(session.queries.last.page, 1);
    },
  );

  testWidgets(
    'empty filters and offline retained records have distinct status and retry',
    (tester) async {
      final session = AuditReadSession()..empty = true;
      addTearDown(session.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: AuditListScreen(session: session, onSettings: () {}),
        ),
      );
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('No audits available.'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('No audits available.'), findsOneWidget);
      session.empty = false;
      await tester.ensureVisible(find.text('Refresh'));
      await tester.tap(find.text('Refresh'));
      await tester.pumpAndSettle();
      session.offline = true;
      await tester.tap(find.text('Refresh'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Retry'),
        150,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.textContaining('Not refreshed'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);
      await tester.scrollUntilVisible(
        find.text('José 🚚'),
        150,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('José 🚚'), findsOneWidget);
    },
  );

  testWidgets(
    'audit browsing applies explicit search and refetches seven-field detail',
    (tester) async {
      final session = AuditReadSession();
      addTearDown(session.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: AuditListScreen(session: session, onSettings: () {}),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('José 🚚'), findsOneWidget);
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Search audits'),
        '0001',
      );
      expect(session.queries, hasLength(1));
      await tester.tap(find.widgetWithText(FilledButton, 'Search'));
      await tester.pumpAndSettle();
      expect(session.queries.last.driverName, '0001');
      await tester.tap(find.text('José 🚚'));
      await tester.pumpAndSettle();
      for (final label in [
        'Driver Name',
        'Helper Name',
        'Audit Date',
        'Station',
        'Plate Number',
        'Remarks',
        'Audited By',
      ]) {
        await tester.scrollUntilVisible(
          find.text(label),
          150,
          scrollable: find.byType(Scrollable).first,
        );
        expect(find.text(label), findsOneWidget);
      }
      expect(find.text('Original Snapshot'), findsOneWidget);
    },
  );

  testWidgets('missing detail clears record and offers back', (tester) async {
    final session = AuditReadSession()..missing = true;
    addTearDown(session.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: AuditListScreen(session: session, onSettings: () {}),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('José 🚚'));
    await tester.pumpAndSettle();
    expect(find.text('Original Snapshot'), findsNothing);
    expect(find.textContaining('no longer available'), findsOneWidget);
    await tester.tap(find.widgetWithText(OutlinedButton, 'Back to audits'));
    await tester.pumpAndSettle();
    expect(find.text('Driver Audits'), findsOneWidget);
  });
}
