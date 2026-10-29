// Fictional, loopback-only native acceptance. No production endpoint or token
// bypass; passwords come from an ignored, temporary dart-define file.
import 'dart:async';

import 'package:bhli_audit/app/bhli_audit_app.dart';
import 'package:bhli_audit/app/privacy_policy.dart';
import 'package:bhli_audit/core/network/api_client.dart';
import 'package:bhli_audit/core/network/api_failure.dart';
import 'package:bhli_audit/core/network/api_origin.dart';
import 'package:bhli_audit/core/settings/public_settings.dart';
import 'package:bhli_audit/features/audits/audit_draft.dart';
import 'package:bhli_audit/features/audits/audit_mutation_controller.dart';
import 'package:bhli_audit/features/audits/models.dart';
import 'package:bhli_audit/features/auth/session_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:integration_test/integration_test.dart';

const demoOrigin = String.fromEnvironment('DAMS_DEMO_ORIGIN');
const adminPassword = String.fromEnvironment('DAMS_DEMO_ADMIN_PASSWORD');
const auditorPassword = String.fromEnvironment('DAMS_DEMO_AUDITOR_PASSWORD');
const auditorBPassword = String.fromEnvironment('DAMS_DEMO_AUDITOR_B_PASSWORD');
const layoutOnly = bool.fromEnvironment('DAMS_ACCEPTANCE_LAYOUT');
const uiOnly = bool.fromEnvironment('DAMS_ACCEPTANCE_UI_ONLY');
const runId = String.fromEnvironment('DAMS_DEMO_RUN_ID', defaultValue: 'first');
const nativeUiName = 'Fictional Native UI Jos\u00e9 \u674e $runId';

// Test-only adapter: upstream HTTP has completed (including the real backend
// transaction), but the application deliberately receives no usable response.
class LostResponse {
  String? method;
  Completer<void>? hold;
  final reached = Completer<void>();
}

class AfterCommitClient extends http.BaseClient {
  AfterCommitClient(this.fault);
  final LostResponse fault;
  final http.Client _upstream = http.Client();
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final response = await _upstream.send(request);
    if (request.method == fault.method) {
      fault.method = null;
      await response.stream.drain<void>();
      if (!fault.reached.isCompleted) fault.reached.complete();
      await fault.hold?.future;
      throw http.ClientException('Fictional acceptance response lost');
    }
    return response;
  }

  @override
  void close() => _upstream.close();
}

SessionController session({LostResponse? fault}) {
  final origin = ApiOrigin.parse(demoOrigin, allowDebugLoopback: true);
  if (!{'localhost', '127.0.0.1'}.contains(Uri.parse(origin.value).host)) {
    throw StateError('Native acceptance requires a disposable loopback API');
  }
  return SessionController(
    (origin) => ApiClient(
      origin,
      clientFactory: fault == null
          ? http.Client.new
          : () => AfterCommitClient(fault),
    ),
  )..setOrigin(origin);
}

AuditDraft draft(String suffix) => AuditDraft(
  driverName: 'Fictional Native José 李 $suffix $runId',
  helperName: 'Fictional helper',
  auditDate: '2026-10-28',
  station: 'Native Acceptance',
  plateNumber: '000123',
  remarks: 'Fictional Unicode 李 remarks.\n${'Long readable remarks. ' * 100}',
);

Future<void> enter(WidgetTester tester, String label, String value) async {
  final key = ValueKey(
    'audit_${label.replaceAll(' (optional)', '').toLowerCase().replaceAll(' ', '_')}',
  );
  final field = find.byKey(key).evaluate().isNotEmpty
      ? find.byKey(key)
      : find.widgetWithText(TextFormField, label);
  await tester.ensureVisible(field);
  await tester.pumpAndSettle();
  await tester.enterText(field, value);
  await tester.pumpAndSettle();
}

Future<void> tap(WidgetTester tester, Finder target) async {
  FocusManager.instance.primaryFocus?.unfocus();
  await tester.pumpAndSettle();
  await tester.ensureVisible(target);
  await tester.pumpAndSettle();
  await tester.tap(target);
  await tester.pumpAndSettle();
}

Future<void> mount(
  WidgetTester tester,
  SessionController current, {
  ThemeChoice theme = ThemeChoice.light,
}) async {
  await tester.pumpWidget(
    BhliAuditApp(
      key: UniqueKey(),
      session: current,
      settingsStore: MemorySettingsStore(),
      initialSettings: PublicSettings(origin: demoOrigin, theme: theme),
      allowDebugLoopback: true,
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> loginUi(
  WidgetTester tester,
  String username,
  String password,
) async {
  await enter(tester, 'Username', username);
  await enter(tester, 'Password', password);
  await tap(tester, find.widgetWithText(FilledButton, 'Sign in'));
  expect(find.text('Driver Audits'), findsOneWidget);
}

Future<void> search(WidgetTester tester, String value) async {
  await enter(tester, 'Search audits', value);
  await tap(tester, find.widgetWithText(FilledButton, 'Search'));
}

Future<void> openFirstDetail(WidgetTester tester) async {
  // Do not apply .first until a lazy sliver row has actually been built.
  final target = find.text('View audit details');
  await tester.scrollUntilVisible(
    target,
    250,
    scrollable: find.byType(Scrollable).first,
  );
  await tap(tester, target.first);
  expect(find.text('Audit details'), findsOneWidget);
}

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  final enabled = demoOrigin.isNotEmpty;
  if (!layoutOnly && !uiOnly) {
    testWidgets(
      'real API and dropped committed responses preserve mutation contracts',
      (tester) async {
        final fault = LostResponse();
        final owner = session(fault: fault);
        final admin = session();
        final other = session();
        addTearDown(owner.dispose);
        addTearDown(admin.dispose);
        addTearDown(other.dispose);
        await owner.signIn('demo_auditor', auditorPassword);
        await admin.signIn('demo_admin', adminPassword);
        await other.signIn('demo_auditor_b', auditorBPassword);
        expect(owner.user?.role, 'AUDITOR');
        expect(other.user?.id, isNot(owner.user?.id));
        final attempt = PendingAuditCreate(draft('transport'));
        fault.method = 'POST';
        await expectLater(
          owner.createAudit(attempt),
          throwsA(isA<AuditMutationFailure>()),
        );
        expect(owner.mutations.state.phase, AuditMutationPhase.unknown);
        expect(owner.mutations.pendingCreate, same(attempt));
        final page = await admin.fetchAudits(
          AuditQuery(driverName: 'transport $runId'),
        );
        expect(page.total, 1);
        final original = await admin.fetchAudit(page.items.single.id);
        expect(original.auditedByUserId, owner.user!.id);
        await admin.updateAudit(
          original.id,
          original.etag!,
          AuditPatch.fromJson({
            'helper_name': 'Edited after original creation',
          }),
        );
        final replay = await owner.mutations.retryCreate();
        expect(replay.replayed, isTrue);
        expect(replay.record.helperName, 'Edited after original creation');
        expect(
          (await owner.fetchAuditHistory(original.id)).items
              .where((e) => e.action == 'CREATE'),
          hasLength(1),
        );
        await expectLater(
          other.updateAudit(
            original.id,
            replay.record.etag!,
            AuditPatch.fromJson({'station': 'Forbidden'}),
          ),
          throwsA(
            isA<AuditMutationFailure>().having(
              (e) => e.failure.status,
              'status',
              403,
            ),
          ),
        );
        fault.method = 'PATCH';
        await expectLater(
          owner.updateAudit(
            original.id,
            replay.record.etag!,
            AuditPatch.fromJson({'remarks': null}),
          ),
          throwsA(isA<AuditMutationFailure>()),
        );
        final latest = await owner.reviewMutation();
        expect(latest.remarks, isNull);
        owner.mutations.acknowledgeReview();
        final duplicate = await owner.createAudit(
          PendingAuditCreate(draft('duplicate plate')),
        );
        expect(duplicate.record.id, isNot(original.id));
        expect(duplicate.record.plateNumber, original.plateNumber);
        // Real stale write is never silently rebased.
        await admin.updateAudit(
          original.id,
          latest.etag!,
          AuditPatch.fromJson({'station': 'Concurrent administrator change'}),
        );
        await expectLater(
          owner.updateAudit(
            original.id,
            latest.etag!,
            AuditPatch.fromJson({'driver_name': 'Stale write'}),
          ),
          throwsA(
            isA<AuditMutationFailure>().having(
              (e) => e.failure.status,
              'status',
              412,
            ),
          ),
        );
        final reviewed = await owner.reviewMutation();
        expect(reviewed.station, 'Concurrent administrator change');
        owner.mutations.acknowledgeReview();
        // DELETE response is lost after the actual server has committed.
        final deletionFault = LostResponse()..method = 'DELETE';
        final deletingAdmin = session(fault: deletionFault);
        addTearDown(deletingAdmin.dispose);
        await deletingAdmin.signIn('demo_admin', adminPassword);
        await expectLater(
          deletingAdmin.deleteAudit(original.id, reviewed.etag!),
          throwsA(isA<AuditMutationFailure>()),
        );
        expect(deletingAdmin.mutations.state.phase, AuditMutationPhase.unknown);
        final archived = await deletingAdmin.reviewMutation();
        expect(archived.deletedAt, isNotNull);
        expect(archived.auditedByName, original.auditedByName);
        await expectLater(
          other.fetchAudit(original.id),
          throwsA(isA<ApiFailure>().having((e) => e.status, 'status', 404)),
        );
        await expectLater(
          other.fetchAuditHistory(original.id, includeDeleted: true),
          throwsA(isA<ApiFailure>().having((e) => e.status, 'status', 403)),
        );
        final history = await admin.fetchAuditHistory(
          original.id,
          includeDeleted: true,
        );
        expect(history.items.first.action, 'CREATE');
        expect(history.items.last.action, 'DELETE');
        expect(history.items.last.actorUserId, admin.user!.id);
        expect(history.items.where((e) => e.action == 'CREATE'), hasLength(1));
        // Hold a genuine committed response while logging out and switching user.
        final held = LostResponse()
          ..method = 'POST'
          ..hold = Completer<void>();
        final switching = session(fault: held);
        addTearDown(switching.dispose);
        await switching.signIn('demo_auditor', auditorPassword);
        final pending = switching.createAudit(
          PendingAuditCreate(draft('late response')),
        );
        final canceled = expectLater(
          pending,
          throwsA(isA<AuditMutationFailure>()),
        );
        await held.reached.future;
        await switching.signOut();
        await switching.signIn('demo_auditor_b', auditorBPassword);
        held.hold!.complete();
        await canceled;
        expect(switching.user?.username, 'demo_auditor_b');
        expect(switching.mutations.pendingCreate, isNull);
        expect(switching.mutations.state.phase, AuditMutationPhase.idle);
        await switching.signOut();
        await deletingAdmin.signOut();
        await other.signOut();
        await owner.signOut();
        await admin.signOut();
      },
      skip: !enabled,
    );
  }
  if (!layoutOnly) {
    testWidgets(
      'native three-account create conflict archive and history walkthrough',
      (tester) async {
        final current = session();
        final admin = session();
        addTearDown(current.dispose);
        addTearDown(admin.dispose);
        final privacy = NativePrivacyGuard(current, requested: true);
        addTearDown(privacy.dispose);
        await binding.convertFlutterSurfaceToImage();
        await admin.signIn('demo_admin', adminPassword);
        await mount(tester, current, theme: ThemeChoice.dark);
        await loginUi(tester, 'demo_auditor', auditorPassword);
        await tap(tester, find.text('New Audit'));
        await tap(tester, find.widgetWithText(FilledButton, 'Save'));
        expect(find.text('Check these fields before saving:'), findsOneWidget);
        await binding.takeScreenshot('phase4b-auditor-validation');
        await enter(tester, 'Driver Name', nativeUiName);
        await enter(tester, 'Helper Name (optional)', 'Fictional helper');
        await enter(tester, 'Audit Date', '2026-10-28');
        await enter(tester, 'Station', 'Native UI');
        await enter(tester, 'Plate Number', '000123');
        await enter(
          tester,
          'Remarks (optional)',
          'Fictional long remarks 李.\n${'Readable Unicode remarks. ' * 80}',
        );
        await binding.takeScreenshot('phase4b-auditor-create');
        await tap(tester, find.widgetWithText(FilledButton, 'Save'));
        expect(find.text('Audit details'), findsOneWidget);
        final created = (await current.fetchAudits(
          AuditQuery(driverName: nativeUiName),
        )).items.single;
        final originalName = created.auditedByName;
        await tap(tester, find.text('Edit'));
        await enter(tester, 'Helper Name (optional)', 'Owner proposal 李');
        final concurrent = await admin.fetchAudit(created.id);
        await admin.updateAudit(
          created.id,
          concurrent.etag!,
          AuditPatch.fromJson({
            'helper_name': 'Other saved helper',
            'station': 'Preserved concurrent station',
          }),
        );
        await tap(tester, find.widgetWithText(FilledButton, 'Save'));
        expect(find.text('Save reviewed changes'), findsOneWidget);
        await binding.takeScreenshot('phase4b-auditor-conflict');
        await tap(tester, find.text('Use my proposed value'));
        await tap(tester, find.text('Save reviewed changes'));
        expect(find.text('Audit details'), findsOneWidget);
        final updated = await current.fetchAudit(created.id);
        expect(updated.helperName, 'Owner proposal 李');
        expect(updated.station, 'Preserved concurrent station');
        expect(updated.auditedByName, originalName);
        await binding.takeScreenshot('phase4b-auditor-owned-details');
        // Same record is shared, but a second AUDITOR cannot edit it.
        await current.signOut();
        await tester.pumpAndSettle();
        await loginUi(tester, 'demo_auditor_b', auditorBPassword);
        await search(tester, nativeUiName);
        await openFirstDetail(tester);
        expect(find.text('Edit'), findsNothing);
        expect(find.text('Archive audit'), findsNothing);
        await binding.takeScreenshot('phase4b-auditor-b-read-only');
        await tap(tester, find.text('History'));
        expect(find.text('Audit history'), findsOneWidget);
        await binding.takeScreenshot('phase4b-auditor-history');
        var growing = await admin.fetchAudit(created.id);
        for (var index = 0; index < 9; index++) {
          growing = await admin.updateAudit(
            growing.id,
            growing.etag!,
            AuditPatch.fromJson({
              'remarks':
                  'Fictional history revision $index \u674e. ${'Long history remarks. ' * 80}',
            }),
          );
        }
        await current.signOut();
        await tester.pumpAndSettle();
        await mount(tester, current);
        await loginUi(tester, 'demo_admin', adminPassword);
        await search(tester, nativeUiName);
        await openFirstDetail(tester);
        await tap(tester, find.text('Archive audit'));
        expect(find.text('Archive this audit?'), findsOneWidget);
        await binding.takeScreenshot('phase4b-admin-archive-confirm');
        await tap(tester, find.widgetWithText(FilledButton, 'Archive audit'));
        expect(find.textContaining('Audit archived.'), findsWidgets);
        await tester.pageBack();
        await tester.pumpAndSettle();
        await tap(tester, find.text('Include archived'));
        await openFirstDetail(tester);
        expect(find.text('Archived · Read-only'), findsOneWidget);
        expect(find.text('Edit'), findsNothing);
        await binding.takeScreenshot('phase4b-admin-archived-details');
        await tap(tester, find.text('History'));
        expect(find.text('Audit history'), findsOneWidget);
        await binding.takeScreenshot('phase4b-admin-archived-history');
        await tester.scrollUntilVisible(
          find.text('Next'),
          350,
          scrollable: find.byType(Scrollable).first,
        );
        await tap(tester, find.text('Next'));
        await tester.scrollUntilVisible(
          find.textContaining('Page 2 of 2'),
          250,
          scrollable: find.byType(Scrollable).first,
        );
        expect(find.textContaining('Page 2 of 2'), findsOneWidget);
        await binding.takeScreenshot('phase4b-admin-history-page2');
        await current.signOut();
        await tester.pumpAndSettle();
        expect(find.widgetWithText(TextFormField, 'Password'), findsOneWidget);
        await binding.takeScreenshot('phase4b-signed-out');
        await admin.signOut();
      },
      skip: !enabled,
    );
  }

  if (!uiOnly) {
    testWidgets('native responsive history and keyboard-safe dirty Back', (
      tester,
    ) async {
      final current = session();
      addTearDown(current.dispose);
      final privacy = NativePrivacyGuard(current, requested: true);
      addTearDown(privacy.dispose);
      await binding.convertFlutterSurfaceToImage();
      await mount(tester, current);
      await loginUi(tester, 'demo_admin', adminPassword);
      await tap(tester, find.text('New Audit'));
      await enter(tester, 'Driver Name', 'Fictional unsent native draft 李');
      // A real native text field is focused; keyboard/Back and dirty cancellation
      // are inspected separately from operator acceptance.
      await binding.takeScreenshot('phase4b-layout-dirty-form');
      FocusManager.instance.primaryFocus?.unfocus();
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Remarks (optional)'));
      await tester.pumpAndSettle();
      await binding.takeScreenshot('phase4b-layout-optional-remarks');
      await tap(tester, find.text('Cancel'));
      expect(find.text('Discard changes?'), findsOneWidget);
      await tap(tester, find.text('Keep editing'));
      expect(find.text('Fictional unsent native draft 李'), findsOneWidget);
      await tap(tester, find.byTooltip('Back'));
      await tap(tester, find.text('Leave'));
      await tap(tester, find.text('Include archived'));
      await search(tester, 'Fictional Deleted Example');
      await binding.takeScreenshot('phase4b-layout-search');
      await openFirstDetail(tester);
      await tap(tester, find.text('History'));
      await tap(tester, find.text('View changes and UTC time').first);
      await binding.takeScreenshot('phase4b-layout-history');
      await SystemChrome.setPreferredOrientations([
        DeviceOrientation.landscapeLeft,
      ]);
      await tester.pumpAndSettle(const Duration(seconds: 2));
      await binding.takeScreenshot('phase4b-layout-landscape');
      expect(tester.takeException(), isNull);
      await SystemChrome.setPreferredOrientations([
        DeviceOrientation.portraitUp,
      ]);
      await tester.pumpAndSettle(const Duration(seconds: 2));
      await current.signOut();
      await tester.pumpAndSettle();
    }, skip: !enabled);
  }
}
