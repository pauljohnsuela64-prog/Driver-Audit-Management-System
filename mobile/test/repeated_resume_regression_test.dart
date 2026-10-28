import 'dart:async';

import 'package:bhli_audit/app/bhli_audit_app.dart';
import 'package:bhli_audit/core/network/api_client.dart';
import 'package:bhli_audit/core/network/api_origin.dart';
import 'package:bhli_audit/core/settings/public_settings.dart';
import 'package:bhli_audit/features/auth/session_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'network_test_support.dart';

void main() {
  testWidgets(
    'repeated resume keeps records concealed until pending identity check completes',
    (tester) async {
      final verified = Completer<http.StreamedResponse>();
      var delayIdentity = false;
      final session = SessionController(
        (origin) => ApiClient(
          origin,
          clientFactory: () => RecordingClient((request) {
            if (request.url.path == '/auth/me' && delayIdentity)
              return verified.future;
            return switch (request.url.path) {
              '/auth/login' => jsonResponse(leaseJson()),
              '/auth/me' => jsonResponse(userJson()),
              '/audits' => jsonResponse({
                'items': [auditJson()],
                'total': 1,
                'page': 1,
                'page_size': 25,
              }),
              _ => jsonResponse(null, status: 204),
            };
          }),
        ),
        clock: () => DateTime.utc(2026, 10, 28, 12),
      );
      addTearDown(session.dispose);
      session.setOrigin(ApiOrigin.parse('https://example.com'));
      await session.signIn('fictional', 'password');
      await tester.pumpWidget(
        BhliAuditApp(
          session: session,
          settingsStore: MemorySettingsStore(),
          initialSettings: const PublicSettings(origin: 'https://example.com'),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Driver Audits'), findsOneWidget);
      delayIdentity = true;
      for (var cycle = 0; cycle < 2; cycle++) {
        for (final state in [
          AppLifecycleState.inactive,
          AppLifecycleState.hidden,
          AppLifecycleState.paused,
        ]) {
          tester.binding.handleAppLifecycleStateChanged(state);
        }
        await tester.pump();
        for (final state in [
          AppLifecycleState.hidden,
          AppLifecycleState.inactive,
          AppLifecycleState.resumed,
        ]) {
          tester.binding.handleAppLifecycleStateChanged(state);
        }
        await tester.pump();
      }
      // Complete the request before asserting so a failing regression leaves no timers.
      final concealed = find.text('Driver Audits').evaluate().isEmpty;
      verified.complete(jsonResponse(userJson()));
      await tester.pumpAndSettle();
      expect(
        concealed,
        isTrue,
        reason: 'A second resume must await the in-flight identity validation.',
      );
      expect(find.text('Driver Audits'), findsOneWidget);
    },
  );
}
