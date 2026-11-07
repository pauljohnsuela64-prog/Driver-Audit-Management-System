import 'package:bhli_audit/offline/app.dart';
import 'package:bhli_audit/offline/repository.dart';

import 'dart:async';
import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/reporting.dart';
import 'package:bhli_audit/offline/report_screen.dart';

class Reports implements OfflineReportingRepository {
  int calls = 0;
  @override
  Future<OfflineReportSnapshot> reportSnapshot(
    AuditFilter filter, {
    bool includeRows = false,
    bool Function()? cancel,
  }) async {
    calls++;
    return OfflineReportSnapshot(
      filter: filter,
      snapshotUtc: DateTime.utc(2026, 11, 6),
      total: 3,
      active: 2,
      archived: 1,
      displayed: 2,
      stations: const [ReportStation('North', 2)],
      rows: [],
      hasRows: includeRows,
    );
  }
}

class EmptyReports implements OfflineReportingRepository {
  @override
  Future<OfflineReportSnapshot> reportSnapshot(
    AuditFilter filter, {
    bool includeRows = false,
    bool Function()? cancel,
  }) async => OfflineReportSnapshot(
    filter: filter,
    snapshotUtc: DateTime.utc(2026),
    total: 0,
    active: 0,
    archived: 0,
    displayed: 0,
    stations: [],
    rows: [],
    hasRows: includeRows,
  );
}

class Documents extends ReportDocuments {
  Documents({this.fail = false, this.wait = false});
  final bool fail, wait;
  final finished = Completer<void>(),
      selected = Completer<void>(),
      release = Completer<bool>();
  bool deleted = false, canceled = false;
  @override
  Future<String> stage(Uint8List bytes) async {
    expect(utf8.decode(bytes), contains('Zero matching audits.'));
    return 'generated-stage';
  }

  @override
  Future<bool> save(String path, {int remainingMillis = 600000}) async {
    selected.complete();
    if (wait) return release.future;
    if (fail) throw PlatformException(code: 'cleanup_incomplete');
    return true;
  }

  @override
  Future<void> deleteStage(String path) async {
    expect(path, 'generated-stage');
    deleted = true;
    finished.complete();
  }

  @override
  Future<void> cancel() async {
    canceled = true;
  }
}

class AppReports extends EmptyReports implements OfflineRepository {
  AuditFilter? requested;
  @override
  Future<LocalProfile?> profile() async =>
      const LocalProfile(id: 'fictional', name: 'Fictional Auditor');
  @override
  Future<AuditPage> list(AuditFilter filter) async => AuditPage(
    items: [],
    total: 0,
    page: filter.page,
    pageSize: filter.pageSize,
  );
  @override
  Future<OfflineReportSnapshot> reportSnapshot(
    AuditFilter filter, {
    bool includeRows = false,
    bool Function()? cancel,
  }) {
    requested = filter;
    return super.reportSnapshot(
      filter,
      includeRows: includeRows,
      cancel: cancel,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class CleanupFailures extends Documents {
  CleanupFailures() : super(fail: true);
  @override
  Future<void> deleteStage(String path) async {
    await super.deleteStage(path);
    throw PlatformException(code: 'cleanup');
  }
}

Future<void> waitFor(WidgetTester tester, bool Function() done) async {
  for (var i = 0; i < 200 && !done(); i++) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 10)),
    );
    await tester.pump();
  }
  expect(done(), true);
}

void main() {
  testWidgets('public and private cleanup failures both retain guidance', (
    tester,
  ) async {
    final docs = CleanupFailures();
    await tester.pumpWidget(
      MaterialApp(
        home: OfflineReportScreen(
          repository: EmptyReports(),
          filter: const AuditFilter(),
          documents: docs,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Save text report'));
    await tester.tap(find.text('Save text report'));
    await tester.pump();
    await waitFor(tester, () => docs.finished.isCompleted);
    await tester.pumpAndSettle();
    expect(
      find.textContaining('incomplete newly created document'),
      findsOneWidget,
    );
    expect(find.textContaining('app-private temporary report'), findsOneWidget);
  });
  testWidgets(
    'report requires applied filters and returns to the same Driver Audits query',
    (tester) async {
      final repo = AppReports();
      await tester.pumpWidget(OfflineApp(repository: repo));
      await tester.pumpAndSettle();
      Future<void> tap(String label) async {
        await tester.ensureVisible(find.text(label));
        await tester.tap(find.text(label));
        await tester.pumpAndSettle();
      }

      await tap('Filters');
      await tester.enterText(
        find.byKey(const ValueKey('offline_filter_driver')),
        'Pending driver',
      );
      await tap('View report summary');
      expect(repo.requested, isNull);
      expect(find.textContaining('Apply or discard'), findsOneWidget);
      await tap('Apply filters');
      await tap('View report summary');
      expect(repo.requested?.driver, 'Pending driver');
      expect(find.text('Report summary'), findsOneWidget);
      await tap('Return to Driver Audits');
      expect(find.text('View report summary'), findsOneWidget);
      await tap('Filters');
      expect(
        tester
            .widget<TextFormField>(
              find.byKey(const ValueKey('offline_filter_driver')),
            )
            .controller
            ?.text,
        'Pending driver',
      );
    },
  );

  for (final fail in [false, true]) {
    testWidgets(
      'save completion cleans owned stage and reports verified result or cleanup failure $fail',
      (tester) async {
        final docs = Documents(fail: fail);
        await tester.pumpWidget(
          MaterialApp(
            home: OfflineReportScreen(
              repository: EmptyReports(),
              filter: const AuditFilter(),
              documents: docs,
            ),
          ),
        );
        await tester.pumpAndSettle();
        await tester.ensureVisible(find.text('Save text report'));
        await tester.tap(find.text('Save text report'));
        await tester.pump();
        await waitFor(tester, () => docs.finished.isCompleted);
        await tester.pumpAndSettle();
        expect(docs.deleted, true);
        expect(
          find.textContaining(
            fail
                ? 'incomplete newly created document'
                : 'Text report saved and verified',
          ),
          findsOneWidget,
        );
      },
    );
  }
  testWidgets(
    'busy report prevents navigation and late cancel preserves completed-save result',
    (tester) async {
      final docs = Documents(wait: true);
      await tester.pumpWidget(
        MaterialApp(
          home: OfflineReportScreen(
            repository: EmptyReports(),
            filter: const AuditFilter(),
            documents: docs,
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Save text report'));
      await tester.tap(find.text('Save text report'));
      await tester.pump();
      await waitFor(tester, () => docs.selected.isCompleted);
      await tester.pump();
      expect(
        tester.widget<PopScope>(find.byType(PopScope).first).canPop,
        false,
      );
      await tester.ensureVisible(find.text('Cancel report'));
      await tester.tap(find.text('Cancel report'));
      await tester.pump();
      expect(docs.canceled, true);
      docs.release.complete(true);
      await tester.pump();
      await waitFor(tester, () => docs.finished.isCompleted);
      await tester.pumpAndSettle();
      expect(
        find.textContaining('Text report saved and verified'),
        findsOneWidget,
      );
    },
  );
  for (final brightness in Brightness.values) {
    testWidgets('summary readable at 320dp and 200% $brightness', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(320, 640);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final repo = Reports();
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData(brightness: brightness),
          home: MediaQuery(
            data: const MediaQueryData(textScaler: TextScaler.linear(2)),
            child: OfflineReportScreen(
              repository: repo,
              filter: const AuditFilter(driver: 'Applied driver'),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.textContaining('Applied driver'),
        100,
      );
      expect(find.textContaining('Applied driver'), findsOneWidget);
      await tester.scrollUntilVisible(find.text('Save text report'), 200);
      expect(find.text('Save text report'), findsOneWidget);
      expect(tester.takeException(), isNull);
      expect(repo.calls, 1);
    });
  }
}
