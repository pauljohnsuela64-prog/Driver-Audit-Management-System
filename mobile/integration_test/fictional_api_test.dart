// Native acceptance only: start scripts.mobile_demo with these fictional
// passwords and ADB-reverse its loopback port. Never point this at real data.
import 'package:bhli_audit/app/bhli_audit_app.dart';
import 'package:bhli_audit/app/privacy_policy.dart';
import 'package:bhli_audit/core/network/api_client.dart';
import 'package:bhli_audit/core/network/api_origin.dart';
import 'package:bhli_audit/core/settings/public_settings.dart';
import 'package:bhli_audit/features/audits/models.dart';
import 'package:bhli_audit/features/auth/session_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  const originText = String.fromEnvironment('DAMS_DEMO_ORIGIN');
  testWidgets('both roles read real fictional pages and historical details', (
    tester,
  ) async {
    final origin = ApiOrigin.parse(originText, allowDebugLoopback: true);
    expect(Uri.parse(origin.value).host, anyOf('127.0.0.1', 'localhost'));
    final session = SessionController(ApiClient.new);
    addTearDown(session.dispose);
    session.setOrigin(origin);
    final privacy = NativePrivacyGuard(session, requested: true);
    addTearDown(privacy.dispose);
    await binding.convertFlutterSurfaceToImage();
    for (final account in [
      ('demo_admin', 'Fictional admin acceptance 2026!'),
      ('demo_auditor', 'Fictional auditor acceptance 2026!'),
    ]) {
      await session.signIn(account.$1, account.$2);
      expect(session.user?.username, account.$1);
      final first = await session.fetchAudits(AuditQuery());
      final next = await session.fetchAudits(AuditQuery(page: 2));
      expect(first.total, 60);
      expect(first.items.length, 25);
      expect(next.items.length, 25);
      expect(
        first.items
            .map((row) => row.id)
            .toSet()
            .intersection(next.items.map((row) => row.id).toSet()),
        isEmpty,
      );
      final detail = await session.fetchAudit(first.items.first.id);
      expect(detail.auditedByName, first.items.first.auditedByName);
      await tester.pumpWidget(
        BhliAuditApp(
          key: ValueKey(account.$1),
          session: session,
          settingsStore: MemorySettingsStore(),
          initialSettings: PublicSettings(
            origin: origin.value,
            theme: account.$1 == 'demo_admin'
                ? ThemeChoice.light
                : ThemeChoice.dark,
          ),
          allowDebugLoopback: true,
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Driver Audits'), findsOneWidget);
      expect(find.text('Create Audit'), findsNothing);
      await binding.takeScreenshot('${account.$1}-audits');
      final details = find.text('View audit details').first;
      await tester.ensureVisible(details);
      await tester.tap(details);
      await tester.pumpAndSettle();
      expect(find.text('Audit details'), findsOneWidget);
      await binding.takeScreenshot('${account.$1}-details');
      await session.signOut();
      await tester.pumpAndSettle();
      expect(find.widgetWithText(TextFormField, 'Password'), findsOneWidget);
      await binding.takeScreenshot('${account.$1}-signed-out');
    }
  }, skip: originText.isEmpty);
}
