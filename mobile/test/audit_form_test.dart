import 'package:bhli_audit/features/audits/audit_form_controller.dart';
import 'package:bhli_audit/features/audits/audit_form_screen.dart';
import 'package:bhli_audit/features/auth/session_controller.dart';
import 'package:bhli_audit/core/network/api_client.dart';
import 'package:bhli_audit/core/network/api_origin.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:bhli_audit/ui/core/audit_theme.dart';
import 'package:flutter_test/flutter_test.dart';

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:bhli_audit/features/audits/models.dart';

import 'network_test_support.dart';

void main() {
  late SessionController session;
  late FutureOr<http.StreamedResponse> Function(http.BaseRequest) handler;
  setUp(() async {
    handler = (_) => jsonResponse(auditJson(), headers: {'etag': '"3"'});
    session = SessionController(
      (origin) => ApiClient(
        origin,
        clientFactory: () => RecordingClient(
          (r) => r.url.path == '/auth/login'
              ? jsonResponse(leaseJson())
              : r.url.path == '/auth/me'
              ? jsonResponse(userJson())
              : handler(r),
        ),
      ),
      clock: () => DateTime.utc(2026, 10, 28, 12),
    )..setOrigin(ApiOrigin.parse('https://example.com'));
    await session.signIn('fictional', 'password');
  });
  tearDown(() => session.dispose());
  test(
    'field validation rejects oversized Unicode and invalid calendar date',
    () {
      final form = AuditFormController(session: session);
      expect(form.validateField('driver_name', ' '), isNotNull);
      expect(form.validateField('helper_name', ' '), isNull);
      expect(form.validateField('driver_name', '\u{1f69a}' * 201), isNotNull);
      expect(form.validateField('audit_date', '2026-02-29'), isNotNull);
      expect(form.validateField('audit_date', '1000-01-01'), isNull);
      form.dispose();
    },
  );
  testWidgets('six fields and immutable current attribution render', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(home: AuditFormScreen(session: session)),
    );
    expect(find.byType(TextFormField), findsNWidgets(6));
    expect(find.text('Current Account Name'), findsOneWidget);
    expect(find.text('Driver Name'), findsOneWidget);
    expect(find.text('Helper Name (optional)'), findsOneWidget);
    expect(find.text('Audit Date'), findsOneWidget);
    expect(find.text('Station'), findsOneWidget);
    expect(find.text('Plate Number'), findsOneWidget);
    expect(find.text('Remarks (optional)'), findsOneWidget);
  });
  testWidgets('logout clears sensitive form text in standalone route', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(home: AuditFormScreen(session: session)),
    );
    await tester.enterText(
      find.byType(TextFormField).first,
      'Sensitive driver',
    );
    await session.signOut();
    await tester.pumpAndSettle();
    expect(find.text('Sensitive driver'), findsNothing);
  });
  testWidgets(
    'signed-out standalone form never renders a supplied sensitive record',
    (tester) async {
      await session.signOut();
      await tester.pumpWidget(
        MaterialApp(
          home: AuditFormScreen(
            session: session,
            record: AuditRecord.fromJson(auditJson(), etag: '"3"'),
          ),
        ),
      );
      expect(find.text('Fictional North'), findsNothing);
      expect(find.text('Original Snapshot'), findsNothing);
    },
  );
  test(
    'edit sends only normalized changed fields with original etag',
    () async {
      final writes = <http.Request>[];
      handler = (r) {
        writes.add(r as http.Request);
        return jsonResponse(
          {...auditJson(), 'version': 4, 'station': 'New Station'},
          headers: {'etag': '"4"'},
        );
      };
      final form = AuditFormController(
        session: session,
        record: AuditRecord.fromJson(auditJson(), etag: '"3"'),
      );
      form.values['station'] = '  New Station  ';
      final result = await form.save();
      expect(result?.record.id, 1);
      expect(writes.single.headers['if-match'], '"3"');
      expect(jsonDecode(writes.single.body), {'station': 'New Station'});
      form.dispose();
    },
  );
  test('unchanged edit never sends an empty patch', () async {
    var writes = 0;
    handler = (_) {
      writes++;
      return jsonResponse(auditJson());
    };
    final form = AuditFormController(
      session: session,
      record: AuditRecord.fromJson(auditJson(), etag: '"3"'),
    );
    expect(await form.save(), isNull);
    expect(writes, 0);
    form.dispose();
  });
  test('unknown create freezes payload and retry keeps same key', () async {
    final keys = <String>[];
    handler = (r) {
      keys.add(r.headers['idempotency-key']!);
      if (keys.length == 1) throw StateError('lost');
      return jsonResponse(auditJson(), headers: {'etag': '"3"'});
    };
    final form = AuditFormController(session: session);
    form.values.addAll({
      'driver_name': 'Driver',
      'audit_date': '2026-10-28',
      'station': 'Station',
      'plate_number': '001',
    });
    expect(await form.save(), isNull);
    expect(form.frozen, isTrue);
    final attempt = session.mutations.pendingCreate;
    final result = await form.save();
    expect(result, isNotNull);
    expect(keys, [attempt!.key, attempt.key]);
    form.dispose();
  });
  test('conflict retains draft and disables any resubmission', () async {
    var writes = 0;
    handler = (_) {
      writes++;
      return jsonResponse({}, status: 412);
    };
    final form = AuditFormController(
      session: session,
      record: AuditRecord.fromJson(auditJson(), etag: '"3"'),
    );
    form.values['station'] = 'My draft';
    expect(await form.save(), isNull);
    expect(form.values['station'], 'My draft');
    expect(form.canSave, isFalse);
    expect(await form.save(), isNull);
    expect(writes, 1);
    form.dispose();
  });
  testWidgets('invalid submit shows linked error summary', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: AuditFormScreen(session: session)),
    );
    await tester.ensureVisible(find.text('Save'));
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(find.text('Check these fields before saving:'), findsOneWidget);
    expect(
      tester
          .widget<TextField>(find.byType(TextField).first)
          .focusNode!
          .hasFocus,
      isTrue,
    );
  });
  test(
    'resumed conflicting create cannot retry without closing and review',
    () async {
      handler = (_) => jsonResponse({}, status: 409);
      final first = AuditFormController(session: session);
      first.values.addAll({
        'driver_name': 'Driver',
        'audit_date': '2026-10-28',
        'station': 'Station',
        'plate_number': '001',
      });
      await first.save();
      final resumed = AuditFormController(
        session: session,
        pendingCreate: session.mutations.pendingCreate,
      );
      expect(resumed.canSave, isFalse);
      resumed.dispose();
      first.dispose();
    },
  );
  testWidgets('dirty Back offers discard while Keep editing retains input', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(home: AuditFormScreen(session: session)),
    );
    await tester.enterText(find.byType(TextFormField).first, 'Draft driver');
    tester.testTextInput.hide();
    await tester.tap(find.byTooltip('Back'));
    await tester.pumpAndSettle();
    expect(find.text('Discard changes?'), findsOneWidget);
    await tester.tap(find.text('Keep editing'));
    await tester.pumpAndSettle();
    expect(find.text('Draft driver'), findsOneWidget);
  });
  testWidgets('date picker and manual calendar input coexist', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: AuditFormScreen(session: session)),
    );
    await tester.enterText(find.byType(TextFormField).at(2), '1000-01-01');
    await tester.tap(find.byTooltip('Choose audit date'));
    await tester.pumpAndSettle();
    expect(find.byType(DatePickerDialog), findsOneWidget);
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    expect(find.text('1000-01-01'), findsOneWidget);
  });
  testWidgets('compact large text form stays scrollable without overflow', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: const TextScaler.linear(2)),
          child: child!,
        ),
        home: AuditFormScreen(session: session),
      ),
    );
    await tester.ensureVisible(find.text('Save'));
    expect(tester.takeException(), isNull);
  });
  testWidgets(
    'save completing over leave dialog returns result to form route',
    (tester) async {
      final completion = Completer<http.StreamedResponse>();
      handler = (_) => completion.future;
      AuditFormResult? saved;
      await tester.pumpWidget(
        MaterialApp(
          home: Navigator(
            onGenerateRoute: (_) => MaterialPageRoute<void>(
              builder: (_) => Builder(
                builder: (context) => Scaffold(
                  body: TextButton(
                    onPressed: () async {
                      saved = await Navigator.push<AuditFormResult>(
                        context,
                        MaterialPageRoute(
                          builder: (_) => AuditFormScreen(
                            session: session,
                            record: AuditRecord.fromJson(
                              auditJson(),
                              etag: '"3"',
                            ),
                          ),
                        ),
                      );
                    },
                    child: const Text('Open'),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextFormField).at(3), 'New Station');
      tester.testTextInput.hide();
      await tester.ensureVisible(find.text('Save'));
      await tester.tap(find.text('Save'));
      await tester.pump();
      await tester.tap(find.byTooltip('Back'));
      await tester.pumpAndSettle();
      expect(find.text('Leave this save attempt?'), findsOneWidget);
      completion.complete(
        jsonResponse(
          {...auditJson(), 'version': 4, 'station': 'New Station'},
          headers: {'etag': '"4"'},
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(saved?.record.version, 4);
      expect(find.text('Open'), findsOneWidget);
    },
  );
  testWidgets('explicit Cancel confirms dirty draft even while IME is open', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(home: AuditFormScreen(session: session)),
    );
    await tester.enterText(find.byType(TextFormField).first, 'Draft');
    tester.view.viewInsets = const FakeViewPadding(bottom: 200);
    addTearDown(tester.view.resetViewInsets);
    await tester.pump();
    await tester.ensureVisible(find.text('Cancel'));
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(find.text('Discard changes?'), findsOneWidget);
  });
  testWidgets('new create warns about process-lifetime interrupted saves', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(home: AuditFormScreen(session: session)),
    );
    expect(
      find.text(
        'If a previous save was interrupted, check Audits before creating again.',
      ),
      findsOneWidget,
    );
  });
  testWidgets('first definitive create422 leaves draft editable', (
    tester,
  ) async {
    handler = (_) => jsonResponse({}, status: 422);
    await tester.pumpWidget(
      MaterialApp(home: AuditFormScreen(session: session)),
    );
    for (final entry in {0: 'Driver', 3: 'Station', 4: '001'}.entries) {
      await tester.enterText(
        find.byType(TextFormField).at(entry.key),
        entry.value,
      );
    }
    await tester.ensureVisible(find.text('Save'));
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(
      tester.widget<TextFormField>(find.byType(TextFormField).first).enabled,
      isTrue,
    );
    expect(find.text('Driver'), findsOneWidget);
  });
  test(
    'unknown create followed by422 retains frozen same-key attempt',
    () async {
      final keys = <String>[];
      handler = (r) {
        keys.add(r.headers['idempotency-key']!);
        if (keys.length == 1) throw StateError('lost response');
        return jsonResponse({}, status: 422);
      };
      final form = AuditFormController(session: session);
      form.values.addAll({
        'driver_name': 'Driver',
        'audit_date': '2026-10-28',
        'station': 'Station',
        'plate_number': '001',
      });
      await form.save();
      final pending = session.mutations.pendingCreate;
      await form.save();
      expect(form.frozen, isTrue);
      expect(session.mutations.pendingCreate, same(pending));
      expect(keys, [pending!.key, pending.key]);
      form.dispose();
    },
  );
  testWidgets('double Save dispatches one write and disables the action', (
    tester,
  ) async {
    final completion = Completer<http.StreamedResponse>();
    var writes = 0;
    handler = (_) {
      writes++;
      return completion.future;
    };
    await tester.pumpWidget(
      MaterialApp(
        home: AuditFormScreen(
          session: session,
          record: AuditRecord.fromJson(auditJson(), etag: '"3"'),
        ),
      ),
    );
    await tester.enterText(find.byType(TextFormField).at(3), 'New Station');
    await tester.ensureVisible(find.text('Save'));
    await tester.tap(find.text('Save'));
    await tester.tap(find.text('Save'));
    await tester.pump();
    expect(writes, 1);
    expect(
      tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
      isNull,
    );
    completion.complete(jsonResponse({}, status: 412));
    await tester.pumpAndSettle();
  });
  testWidgets(
    'leaving pending create retains attempt and ignores late completion',
    (tester) async {
      final completion = Completer<http.StreamedResponse>();
      handler = (_) => completion.future;
      AuditFormResult? result;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () async {
                  result = await Navigator.push<AuditFormResult>(
                    context,
                    MaterialPageRoute(
                      builder: (_) => AuditFormScreen(session: session),
                    ),
                  );
                },
                child: const Text('Open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
      for (final entry in {0: 'Driver', 3: 'Station', 4: '001'}.entries) {
        await tester.enterText(
          find.byType(TextFormField).at(entry.key),
          entry.value,
        );
      }
      tester.testTextInput.hide();
      await tester.ensureVisible(find.text('Save'));
      await tester.tap(find.text('Save'));
      await tester.pump();
      final pending = session.mutations.pendingCreate;
      await tester.tap(find.byTooltip('Back'));
      await tester.pumpAndSettle();
      expect(
        find.descendant(
          of: find.byType(AlertDialog),
          matching: find.textContaining('server may already have saved'),
        ),
        findsOneWidget,
      );
      await tester.tap(find.text('Leave'));
      await tester.pumpAndSettle();
      completion.complete(jsonResponse(auditJson(), headers: {'etag': '"3"'}));
      await tester.pumpAndSettle();
      expect(result, isNull);
      expect(find.text('Open'), findsOneWidget);
      expect(session.mutations.pendingCreate, same(pending));
      expect(tester.takeException(), isNull);
    },
  );
  for (final brightness in Brightness.values) {
    for (final size in [const Size(320, 640), const Size(640, 320)]) {
      testWidgets('form and discard actions at200% $brightness $size', (
        tester,
      ) async {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        await tester.pumpWidget(
          MaterialApp(
            theme: auditTheme(brightness),
            builder: (context, child) => MediaQuery(
              data: MediaQuery.of(context)
                  .copyWith(textScaler: const TextScaler.linear(2)),
              child: child!,
            ),
            home: AuditFormScreen(session: session),
          ),
        );
        await tester.enterText(
          find.byType(TextFormField).first,
          'Fictional Unicode \u674e',
        );
        FocusManager.instance.primaryFocus?.unfocus();
        await tester.pumpAndSettle();
        await tester.ensureVisible(find.text('Cancel'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Cancel'));
        await tester.pumpAndSettle();
        expect(find.text('Discard changes?'), findsOneWidget);
        await tester.ensureVisible(find.text('Keep editing'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Keep editing'));
        await tester.pumpAndSettle();
        expect(find.byType(AlertDialog), findsNothing);
        expect(tester.takeException(), isNull);
      });
    }
  }
  testWidgets('system Back with keyboard preserves dirty form before discard', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(home: AuditFormScreen(session: session)),
    );
    await tester.enterText(find.byType(TextFormField).first, 'Draft');
    tester.view.viewInsets = const FakeViewPadding(bottom: 200);
    addTearDown(tester.view.resetViewInsets);
    await tester.pump();
    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(find.text('Draft'), findsOneWidget);
    expect(
      tester
          .widget<TextField>(find.byType(TextField).first)
          .focusNode!
          .hasFocus,
      isFalse,
    );
  });
  for (final status in [403, 404]) {
    test('edit$status erases denied draft and prevents resubmission', () async {
      var writes = 0;
      handler = (_) {
        writes++;
        return jsonResponse({}, status: status);
      };
      final form = AuditFormController(
        session: session,
        record: AuditRecord.fromJson(auditJson(), etag: '"3"'),
      );
      form.values['station'] = 'Private draft';
      await form.save();
      expect(form.canSave, isFalse);
      expect(form.values.values.where((value) => value != ''), isEmpty);
      expect(form.initial, isEmpty);
      await form.save();
      expect(writes, 1);
      form.dispose();
    });
  }
  testWidgets('optional field labels remain readable at320dp and200percent', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    try {
      tester.view.physicalSize = const Size(320, 640);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context)
                .copyWith(textScaler: const TextScaler.linear(2)),
            child: child!,
          ),
          home: AuditFormScreen(session: session),
        ),
      );
      expect(
        tester.getTopLeft(find.text('Helper Name (optional)')).dy,
        greaterThanOrEqualTo(
          tester.getBottomLeft(find.byType(TextFormField).first).dy + 8,
        ),
      );
      expect(
        tester.getBottomLeft(find.text('Helper Name (optional)')).dy + 8,
        lessThanOrEqualTo(
          tester.getTopLeft(find.byType(TextFormField).at(1)).dy,
        ),
      );
      for (final label in ['Helper Name (optional)', 'Remarks (optional)']) {
        final key = ValueKey(
          'audit_${label.replaceAll(' (optional)', '').toLowerCase().replaceAll(' ', '_')}',
        );
        expect(tester.getSemantics(find.byKey(key)).label, contains(label));
        await tester.ensureVisible(find.text(label));
        await tester.pumpAndSettle();
        expect(
          tester
              .renderObject<RenderParagraph>(find.text(label))
              .didExceedMaxLines,
          isFalse,
          reason: label,
        );
      }
    } finally {
      semantics.dispose();
    }
  });
}
