import 'dart:async';
import 'dart:convert';

import 'package:bhli_audit/core/network/api_client.dart';
import 'package:bhli_audit/core/network/api_origin.dart';
import 'package:bhli_audit/features/auth/session_controller.dart';
import 'package:bhli_audit/features/audits/audit_form_controller.dart';
import 'package:bhli_audit/features/audits/audit_details_screen.dart';
import 'package:bhli_audit/features/audits/audit_form_screen.dart';
import 'package:bhli_audit/features/audits/audit_mutation_controller.dart';
import 'package:bhli_audit/features/audits/audit_list_screen.dart';
import 'package:bhli_audit/features/audits/audit_conflict_screen.dart';
import 'package:bhli_audit/ui/core/audit_theme.dart';
import 'package:bhli_audit/features/audits/models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'network_test_support.dart';

void main() {
  late SessionController session;
  late FutureOr<http.StreamedResponse> Function(http.BaseRequest) handler;
  var role = 'ADMIN';
  Future<void> setup() async {
    handler = (_) => jsonResponse(auditJson(), headers: {'etag': '"3"'});
    session = SessionController(
      (origin) => ApiClient(
        origin,
        clientFactory: () => RecordingClient(
          (r) => r.url.path == '/auth/login'
              ? jsonResponse(leaseJson())
              : r.url.path == '/auth/me'
              ? jsonResponse(userJson(role: role))
              : r.url.path == '/auth/logout'
              ? http.StreamedResponse(const Stream.empty(), 204)
              : handler(r),
        ),
      ),
      clock: () => DateTime.utc(2026, 10, 28, 12),
    )..setOrigin(ApiOrigin.parse('https://example.com'));
    await session.signIn('fictional', 'password');
  }

  tearDown(() => session.dispose());
  Future<void> openConflict(WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () => Navigator.push(
                context,
                MaterialPageRoute<void>(
                  builder: (_) => AuditFormScreen(
                    session: session,
                    record: AuditRecord.fromJson(auditJson(), etag: '"3"'),
                  ),
                ),
              ),
              child: const Text('Open editor'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open editor'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Station'),
      'Mine',
    );
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.ensureVisible(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
  }

  Future<AuditFormController> conflict({bool uncertain = false}) async {
    role = 'ADMIN';
    await setup();
    handler = (r) => r.method == 'PATCH'
        ? uncertain
              ? throw StateError('lost response')
              : jsonResponse({}, status: 412)
        : jsonResponse(
            {
              ...auditJson(),
              'version': 4,
              'station': 'Theirs',
              'driver_name': 'Concurrent driver',
            },
            headers: {'etag': '"4"'},
          );
    final form = AuditFormController(
      session: session,
      record: AuditRecord.fromJson(auditJson(), etag: '"3"'),
    );
    form.values['station'] = 'Mine';
    await form.save();
    await form.reviewLatest();
    return form;
  }

  for (final brightness in Brightness.values) {
    for (final size in [const Size(320, 640), const Size(640, 320)]) {
      testWidgets('long Unicode and null comparison at200% $brightness $size', (
        tester,
      ) async {
        final form = await conflict();
        form.dispose();
        final baseline = AuditRecord.fromJson({
          ...auditJson(),
          'remarks': null,
        }, etag: '"3"');
        // Reuse the authenticated session after explicitly releasing the first review.
        session.mutations.acknowledgeReview();
        final comparison = AuditFormController(
          session: session,
          record: baseline,
        );
        comparison.values['remarks'] = '漢🚚 é\n' * 300;
        handler = (r) => r.method == 'PATCH'
            ? jsonResponse({}, status: 412)
            : jsonResponse(
                {...auditJson(), 'version': 4, 'remarks': null},
                headers: {'etag': '"4"'},
              );
        await comparison.save();
        await comparison.reviewLatest();
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        final semantics = tester.ensureSemantics();
        await tester.pumpWidget(
          MaterialApp(
            theme: auditTheme(brightness),
            home: MediaQuery(
              data: MediaQueryData(
                size: size,
                textScaler: const TextScaler.linear(2),
              ),
              child: Scaffold(
                body: AnimatedBuilder(
                  animation: comparison,
                  builder: (_, _) => AuditConflictScreen(
                    form: comparison,
                    onSave: () {},
                    onDiscard: () {},
                    onRetry: () {},
                  ),
                ),
              ),
            ),
          ),
        );
        expect(find.text('Not provided'), findsOneWidget);
        expect(
          tester
              .widget<FilledButton>(
                find.widgetWithText(FilledButton, 'Save reviewed changes'),
              )
              .onPressed,
          isNull,
        );
        final choice = find.byType(ChoiceChip).first;
        await tester.ensureVisible(choice);
        await tester.pumpAndSettle();
        expect(tester.getSize(choice).height, greaterThanOrEqualTo(48));
        await tester.tap(choice);
        await tester.pumpAndSettle();
        expect(tester.widget<ChoiceChip>(choice).selected, isTrue);
        expect(
          tester
              .widget<FilledButton>(
                find.widgetWithText(FilledButton, 'Save reviewed changes'),
              )
              .onPressed,
          isNotNull,
        );
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox());
        semantics.dispose();
        comparison.dispose();
      });
    }
  }
  testWidgets(
    'logout dismisses root conflict discard dialog and erases proposed values',
    (tester) async {
      role = 'ADMIN';
      await setup();
      handler = (r) => r.method == 'PATCH'
          ? jsonResponse({}, status: 412)
          : jsonResponse(
              {...auditJson(), 'version': 4},
              headers: {'etag': '"4"'},
            );
      await openConflict(tester);
      await tester.tap(find.byTooltip('Back'));
      await tester.pumpAndSettle();
      expect(find.byType(AlertDialog), findsOneWidget);
      await session.signOut();
      await tester.pumpAndSettle();
      expect(find.byType(AlertDialog), findsNothing);
      expect(find.text('Mine'), findsNothing);
      expect(find.text('Original Snapshot'), findsNothing);
    },
  );
  testWidgets(
    'confirmed archive reports actual list refresh failure separately',
    (tester) async {
      role = 'ADMIN';
      await setup();
      var archived = false;
      handler = (r) {
        if (r.method == 'DELETE') {
          archived = true;
          return http.StreamedResponse(const Stream.empty(), 204);
        }
        if (r.url.path == '/audits') {
          return archived
              ? jsonResponse({}, status: 503)
              : jsonResponse({
                  'items': [auditJson()],
                  'total': 1,
                  'page': 1,
                  'page_size': 25,
                });
        }
        return jsonResponse(auditJson(), headers: {'etag': '"3"'});
      };
      await tester.pumpWidget(
        MaterialApp(
          home: AuditListScreen(session: session, onSettings: () {}),
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.textContaining('000123').first);
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('000123').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Archive audit'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Archive audit'));
      await tester.pumpAndSettle();
      expect(
        find.textContaining('Audit archived. The list could not be refreshed.'),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'leaving pending reviewed PATCH cancels waiting and late success stays unconfirmed',
    (tester) async {
      role = 'ADMIN';
      await setup();
      var writes = 0;
      final reply = Completer<http.StreamedResponse>();
      handler = (r) {
        if (r.method == 'PATCH') {
          return ++writes == 1 ? jsonResponse({}, status: 412) : reply.future;
        }
        return jsonResponse(
          {...auditJson(), 'version': 4},
          headers: {'etag': '"4"'},
        );
      };
      await openConflict(tester);
      await tester.ensureVisible(find.text('Use my proposed value'));
      await tester.tap(find.text('Use my proposed value'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Save reviewed changes'));
      await tester.tap(find.text('Save reviewed changes'));
      await tester.pump();
      await tester.tap(find.byTooltip('Back'));
      await tester.pumpAndSettle();
      await tester.tap(
        find.widgetWithText(TextButton, 'Discard my changes').last,
      );
      await tester.pumpAndSettle();
      reply.complete(
        jsonResponse(
          {...auditJson(), 'version': 5, 'station': 'Mine'},
          headers: {'etag': '"5"'},
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Open editor'), findsOneWidget);
      expect(session.mutations.state.phase, AuditMutationPhase.unknown);
    },
  );
  testWidgets('retry latest404 exits editor and does not expose stale record', (
    tester,
  ) async {
    role = 'ADMIN';
    await setup();
    var reads = 0;
    handler = (r) => r.method == 'PATCH'
        ? jsonResponse({}, status: 412)
        : jsonResponse({}, status: ++reads == 1 ? 503 : 404);
    await openConflict(tester);
    await tester.ensureVisible(find.text('Retry latest audit'));
    await tester.tap(find.text('Retry latest audit'));
    await tester.pumpAndSettle();
    expect(find.text('Open editor'), findsOneWidget);
    expect(find.text('Original Snapshot'), findsNothing);
  });
  testWidgets(
    'stale archive requires fresh confirmation and ETag, never automatic DELETE replay',
    (tester) async {
      role = 'ADMIN';
      await setup();
      var reads = 0;
      final deletes = <http.BaseRequest>[];
      handler = (r) {
        if (r.method == 'DELETE') {
          deletes.add(r);
          return deletes.length == 1
              ? jsonResponse({}, status: 412)
              : http.StreamedResponse(const Stream.empty(), 204);
        }
        final version = ++reads < 3 ? 3 : 4;
        return jsonResponse(
          {...auditJson(), 'version': version},
          headers: {'etag': '"$version"'},
        );
      };
      await tester.pumpWidget(
        MaterialApp(home: AuditDetailsScreen(session: session, auditId: 1)),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Archive audit'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Archive audit'));
      await tester.pumpAndSettle();
      expect(deletes.length, 1);
      await tester.tap(find.text('Review archive outcome'));
      await tester.pumpAndSettle();
      expect(deletes.length, 1);
      await tester.tap(find.widgetWithText(FilledButton, 'Archive audit'));
      await tester.pumpAndSettle();
      expect(deletes.map((r) => r.headers['if-match']), ['"3"', '"4"']);
    },
  );
  for (final unavailable in [false, true]) {
    testWidgets(
      'uncertain archive targeted ADMIN verification ${unavailable ? '404 stays unavailable' : 'finds archived read-only'}',
      (tester) async {
        role = 'ADMIN';
        await setup();
        var deletes = 0;
        final reads = <http.BaseRequest>[];
        handler = (r) {
          if (r.method == 'DELETE') {
            deletes++;
            throw StateError('lost response');
          }
          reads.add(r);
          if (r.url.queryParameters['include_deleted'] == 'true') {
            return unavailable
                ? jsonResponse({}, status: 404)
                : jsonResponse(
                    {
                      ...auditJson(),
                      'version': 4,
                      'deleted_at': '2026-10-28T12:01:00Z',
                      'deleted_by_user_id': 8,
                    },
                    headers: {'etag': '"4"'},
                  );
          }
          return jsonResponse(auditJson(), headers: {'etag': '"3"'});
        };
        await tester.pumpWidget(
          MaterialApp(home: AuditDetailsScreen(session: session, auditId: 1)),
        );
        await tester.pumpAndSettle();
        await tester.tap(find.text('Archive audit'));
        await tester.pumpAndSettle();
        await tester.tap(find.widgetWithText(FilledButton, 'Archive audit'));
        await tester.pumpAndSettle();
        expect(find.textContaining('Archive not confirmed'), findsOneWidget);
        await tester.tap(find.text('Review archive outcome'));
        await tester.pumpAndSettle();
        expect(reads.last.url.queryParameters['include_deleted'], 'true');
        expect(deletes, 1);
        expect(find.text('Audit archived.'), findsNothing);
        if (unavailable) {
          expect(find.textContaining('unavailable'), findsOneWidget);
          expect(find.text('Edit'), findsNothing);
        } else {
          expect(find.text('Archived · Read-only'), findsOneWidget);
          expect(find.text('Archive audit'), findsNothing);
        }
      },
    );
  }
  testWidgets('logout dismisses root archive dialog and suppresses DELETE', (
    tester,
  ) async {
    role = 'ADMIN';
    await setup();
    var deletes = 0;
    handler = (r) {
      if (r.method == 'DELETE') deletes++;
      return jsonResponse(auditJson(), headers: {'etag': '"3"'});
    };
    await tester.pumpWidget(
      MaterialApp(
        home: Navigator(
          onGenerateRoute: (_) => MaterialPageRoute<void>(
            builder: (_) => AuditDetailsScreen(session: session, auditId: 1),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Archive audit'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);
    await session.signOut();
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(find.textContaining('000123'), findsNothing);
    expect(deletes, 0);
  });
  testWidgets(
    'role change during archive confirmation dismisses protected dialog',
    (tester) async {
      role = 'ADMIN';
      await setup();
      await tester.pumpWidget(
        MaterialApp(home: AuditDetailsScreen(session: session, auditId: 1)),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Archive audit'));
      await tester.pumpAndSettle();
      role = 'AUDITOR';
      await session.verifyOnResume();
      await tester.pumpAndSettle();
      expect(find.byType(AlertDialog), findsNothing);
      expect(find.text('Archive audit'), findsNothing);
    },
  );
  testWidgets('same-session role downgrade erases targeted archived record', (
    tester,
  ) async {
    role = 'ADMIN';
    await setup();
    handler = (r) {
      if (r.method == 'DELETE') throw StateError('lost');
      return r.url.queryParameters['include_deleted'] == 'true'
          ? jsonResponse(
              {
                ...auditJson(),
                'version': 4,
                'deleted_at': '2026-10-28T12:01:00Z',
                'deleted_by_user_id': 8,
              },
              headers: {'etag': '"4"'},
            )
          : jsonResponse(auditJson(), headers: {'etag': '"3"'});
    };
    await tester.pumpWidget(
      MaterialApp(home: AuditDetailsScreen(session: session, auditId: 1)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Archive audit'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Archive audit'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Review archive outcome'));
    await tester.pumpAndSettle();
    expect(find.text('Archived · Read-only'), findsOneWidget);
    role = 'AUDITOR';
    await session.verifyOnResume();
    await tester.pumpAndSettle();
    expect(find.text('Archived · Read-only'), findsNothing);
    expect(find.textContaining('000123'), findsNothing);
  });

  test(
    'choosing all latest values closes review without empty PATCH',
    () async {
      final form = await conflict();
      var writes = 0;
      handler = (_) {
        writes++;
        return jsonResponse({}, status: 500);
      };
      form.chooseReview('station', false);
      final result = await form.saveReviewed();
      expect(result!.record.station, 'Theirs');
      expect(writes, 0);
      form.dispose();
    },
  );
  test('uncertain PATCH never retries and repeated conflicts reset explicit choices', () async {
    final form = await conflict(uncertain: true);
    var writes = 0;
    handler = (r) {
      if (r.method == 'PATCH') {
        writes++;
        return jsonResponse({}, status: 412);
      }
      return jsonResponse(
        {...auditJson(), 'version': 5, 'station': 'Changed again'},
        headers: {'etag': '"5"'},
      );
    };
    expect(writes, 0);
    form.chooseReview('station', true);
    expect(await form.saveReviewed(), isNull);
    await form.reviewLatest();
    expect(form.canSaveReviewed, isFalse);
    expect(form.proposedValues['station'], 'Mine');
    expect(form.originalValues['station'], 'Fictional North');
    expect(form.latestValues['station'], 'Changed again');
    expect(writes, 1);
    form.dispose();
  });
  test(
    'failed latest fetch keeps proposal and retry requires fresh choices',
    () async {
      final form = await conflict();
      handler = (_) => jsonResponse({}, status: 503);
      await form.reviewLatest();
      expect(form.canSaveReviewed, isFalse);
      expect(form.proposedValues['station'], 'Mine');
      expect(form.message, contains('retained'));
      form.dispose();
    },
  );
  for (final status in [403, 404]) {
    test(
      'latest $status erases unavailable draft and disables review',
      () async {
        final form = await conflict();
        handler = (_) => jsonResponse({}, status: status);
        await form.reviewLatest();
        expect(form.active, isFalse);
        expect(form.values['station'], '');
        expect(form.proposedValues['station'], isNull);
        expect(form.canSaveReviewed, isFalse);
        form.dispose();
      },
    );
  }
  test(
    'logout while latest review pending erases all comparison values',
    () async {
      final form = await conflict();
      final reply = Completer<http.StreamedResponse>();
      handler = (_) => reply.future;
      final review = form.reviewLatest();
      await Future<void>.delayed(Duration.zero);
      await session.signOut();
      reply.complete(
        jsonResponse({...auditJson(), 'version': 5}, headers: {'etag': '"5"'}),
      );
      await review;
      expect(form.latestValues, isEmpty);
      expect(form.proposedValues, isEmpty);
      expect(form.active, isFalse);
      form.dispose();
    },
  );
  testWidgets(
    'comparison identifies unrelated concurrent values and Back confirms explicit discard',
    (tester) async {
      role = 'ADMIN';
      await setup();
      handler = (r) => r.method == 'PATCH'
          ? jsonResponse({}, status: 412)
          : jsonResponse(
              {
                ...auditJson(),
                'version': 4,
                'driver_name': 'Concurrent driver',
              },
              headers: {'etag': '"4"'},
            );
      await tester.pumpWidget(
        MaterialApp(
          home: AuditFormScreen(
            session: session,
            record: AuditRecord.fromJson(auditJson(), etag: '"3"'),
          ),
        ),
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Station'),
        'Mine',
      );
      FocusManager.instance.primaryFocus?.unfocus();
      await tester.ensureVisible(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();
      expect(find.text('Concurrent driver'), findsOneWidget);
      await tester.tap(find.byTooltip('Back'));
      await tester.pumpAndSettle();
      expect(find.text('Continue reviewing'), findsOneWidget);
      await tester.tap(find.text('Continue reviewing'));
      await tester.pumpAndSettle();
      expect(find.text('Mine'), findsOneWidget);
    },
  );
  for (final status in [409, 412]) {
    test(
      'conflict $status reviews each local field and preserves unrelated latest values',
      () async {
        role = 'ADMIN';
        await setup();
        final writes = <http.Request>[];
        handler = (r) {
          if (r.method == 'PATCH') {
            writes.add(r as http.Request);
            if (writes.length == 1) return jsonResponse({}, status: status);
            return jsonResponse(
              {
                ...auditJson(),
                'version': 5,
                'station': 'Mine',
                'driver_name': 'Concurrent driver',
              },
              headers: {'etag': '"5"'},
            );
          }
          return jsonResponse(
            {
              ...auditJson(),
              'version': 4,
              'station': 'Theirs',
              'driver_name': 'Concurrent driver',
            },
            headers: {'etag': '"4"'},
          );
        };
        final form = AuditFormController(
          session: session,
          record: AuditRecord.fromJson(auditJson(), etag: '"3"'),
        );
        form.values['station'] = 'Mine';
        await form.save();
        expect(form.requiresReload, isTrue);
        await form.reviewLatest();
        expect(form.reviewFields, ['station']);
        expect(form.latestValues['station'], 'Theirs');
        expect(form.originalValues['station'], 'Fictional North');
        expect(form.canSaveReviewed, isFalse);
        form.chooseReview('station', true);
        expect(form.canSaveReviewed, isTrue);
        final result = await form.saveReviewed();
        expect(result!.record.driverName, 'Concurrent driver');
        expect(writes.last.headers['if-match'], '"4"');
        expect(jsonDecode(writes.last.body), {'station': 'Mine'});
        form.dispose();
      },
    );
  }
  testWidgets('ADMIN archive reviews current identity and accepts 204', (
    tester,
  ) async {
    role = 'ADMIN';
    await setup();
    final deletes = <http.BaseRequest>[];
    var reads = 0;
    handler = (r) {
      if (r.method == 'DELETE') {
        deletes.add(r);
        return http.StreamedResponse(const Stream.empty(), 204);
      }
      reads++;
      return jsonResponse(
        {...auditJson(), 'version': 4},
        headers: {'etag': '"4"'},
      );
    };
    await tester.pumpWidget(
      MaterialApp(home: AuditDetailsScreen(session: session, auditId: 1)),
    );
    await tester.pumpAndSettle();
    expect(find.text('Archive audit'), findsOneWidget);
    await tester.tap(find.text('Archive audit'));
    await tester.pumpAndSettle();
    expect(reads, 2);
    expect(find.textContaining('000123'), findsWidgets);
    await tester.tap(find.widgetWithText(FilledButton, 'Archive audit').last);
    await tester.pumpAndSettle();
    expect(deletes.single.headers['if-match'], '"4"');
    expect(find.textContaining('Audit archived'), findsWidgets);
    expect(find.text('Edit'), findsNothing);
  });
  testWidgets('AUDITOR never sees archive', (tester) async {
    role = 'AUDITOR';
    await setup();
    await tester.pumpWidget(
      MaterialApp(home: AuditDetailsScreen(session: session, auditId: 1)),
    );
    await tester.pumpAndSettle();
    expect(find.text('Archive audit'), findsNothing);
  });
}
