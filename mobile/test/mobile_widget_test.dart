import 'dart:async';

import 'package:bhli_audit/app/bhli_audit_app.dart';
import 'package:bhli_audit/core/network/api_client.dart';
import 'package:bhli_audit/core/network/api_origin.dart';
import 'package:bhli_audit/core/settings/public_settings.dart';
import 'package:bhli_audit/features/auth/session_controller.dart';
import 'package:bhli_audit/features/settings/settings_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'network_test_support.dart';

class WidgetSettingsStore implements SettingsStore {
  PublicSettings value = const PublicSettings();
  bool fail = false;
  @override
  Future<PublicSettings> load() async => value;
  @override
  Future<void> save(PublicSettings settings) async {
    if (fail) throw const SettingsFailure();
    value = settings;
  }
}

void main() {
  late SessionController session;
  late WidgetSettingsStore settings;
  FutureOr<http.StreamedResponse> Function(http.BaseRequest)? customRead;
  late List<http.BaseRequest> requests;

  setUp(() {
    requests = [];
    settings = WidgetSettingsStore();
    customRead = null;
    session = SessionController(
      (origin) => ApiClient(
        origin,
        clientFactory: () => RecordingClient((request) {
          requests.add(request);
          return customRead?.call(request) ??
              switch (request.url.path) {
                '/auth/login' => jsonResponse(leaseJson()),
                '/auth/me' => jsonResponse(userJson()),
                '/auth/logout' => jsonResponse(null, status: 204),
                '/audits' => jsonResponse({
                  'items': [auditJson()],
                  'total': 1,
                  'page': int.parse(request.url.queryParameters['page']!),
                  'page_size': 25,
                }),
                _ => jsonResponse(auditJson(), headers: {'etag': '"3"'}),
              };
        }),
      ),
      clock: () => DateTime.utc(2026, 10, 28, 12),
    );
  });
  tearDown(() => session.dispose());

  Future<void> pumpApp(
    WidgetTester tester, {
    bool connected = true,
    ThemeChoice theme = ThemeChoice.system,
  }) async {
    if (connected) session.setOrigin(ApiOrigin.parse('https://example.com'));
    await tester.pumpWidget(
      BhliAuditApp(
        session: session,
        settingsStore: settings,
        initialSettings: PublicSettings(
          origin: connected ? 'https://example.com' : null,
          theme: theme,
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> login(WidgetTester tester) async {
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Username'),
      'fictional',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Password'),
      'password',
    );
    await tester.ensureVisible(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pumpAndSettle();
  }

  testWidgets(
    'first launch requires explicit connection and failed save preserves origin',
    (tester) async {
      await pumpApp(tester, connected: false);
      expect(find.text('API origin'), findsOneWidget);
      await tester.enterText(
        find.widgetWithText(TextFormField, 'API origin'),
        'https://new.example.com',
      );
      settings.fail = true;
      await tester.tap(find.widgetWithText(FilledButton, 'Save connection'));
      await tester.pumpAndSettle();
      expect(session.origin, isNull);
      expect(find.textContaining('save'), findsWidgets);
      settings.fail = false;
      await tester.tap(find.widgetWithText(FilledButton, 'Save connection'));
      await tester.pumpAndSettle();
      expect(session.origin!.value, 'https://new.example.com');
      expect(find.text('Username'), findsOneWidget);
    },
  );

  testWidgets(
    'login allows short existing passwords, hiding and failure clears password',
    (tester) async {
      customRead = (_) => jsonResponse({
        'error': {'code': 'unauthorized'},
      }, status: 401);
      await pumpApp(tester);
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Username'),
        'fictional',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Password'),
        '🔑',
      );
      await tester.tap(find.byTooltip('Show password'));
      await tester.pump();
      expect(find.byTooltip('Hide password'), findsOneWidget);
      await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
      await tester.pumpAndSettle();
      expect(requests.where((r) => r.url.path == '/auth/login'), hasLength(1));
      final fields = tester
          .widgetList<TextFormField>(find.byType(TextFormField))
          .toList();
      expect(fields[1].controller!.text, isEmpty);
      expect(fields[0].controller!.text, 'fictional');
    },
  );

  testWidgets(
    'details refetch shows all seven fields and snapshot then back retains filter',
    (tester) async {
      await pumpApp(tester);
      await login(tester);
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Search audits'),
        'Jos',
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Search'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('José 🚚').first,
        150,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('José 🚚').first);
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
      expect(requests.any((r) => r.url.path == '/audits/1'), true);
      await tester.pageBack();
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<TextFormField>(
              find.widgetWithText(TextFormField, 'Search audits'),
            )
            .controller!
            .text,
        'Jos',
      );
    },
  );

  testWidgets(
    'logout clears protected detail route and locks origin until signed out',
    (tester) async {
      await pumpApp(tester);
      await login(tester);
      await tester.tap(find.byTooltip('Settings'));
      await tester.pumpAndSettle();
      expect(find.widgetWithText(TextFormField, 'API origin'), findsNothing);
      expect(find.text('Current Account Name'), findsOneWidget);
      await tester.tap(find.widgetWithText(OutlinedButton, 'Sign out'));
      await tester.pumpAndSettle();
      expect(find.text('Username'), findsOneWidget);
      expect(find.text('Driver Audits'), findsNothing);
    },
  );

  testWidgets(
    'Android back returns from detail through the session navigator',
    (tester) async {
      await pumpApp(tester);
      await login(tester);
      await tester.scrollUntilVisible(
        find.text('José 🚚'),
        150,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('José 🚚'));
      await tester.pumpAndSettle();
      expect(find.text('Audit details'), findsOneWidget);
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.text('Driver Audits'), findsOneWidget);
      expect(find.text('Audit details'), findsNothing);
    },
  );

  testWidgets(
    'connection health is isolated from credentials and disables editing while pending',
    (tester) async {
      final health = Completer<http.StreamedResponse>();
      final healthRequests = <http.BaseRequest>[];
      session.setOrigin(ApiOrigin.parse('https://example.com'));
      await tester.pumpWidget(
        MaterialApp(
          home: SettingsScreen(
            session: session,
            theme: ThemeChoice.system,
            onSaveOrigin: (_) async {},
            onTheme: (_) async {},
            healthClientFactory: (origin) => ApiClient(
              origin,
              clientFactory: () => RecordingClient((request) {
                healthRequests.add(request);
                return health.future;
              }),
            ),
          ),
        ),
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'API origin'),
        'https://health.example.com',
      );
      await tester.tap(find.widgetWithText(OutlinedButton, 'Test connection'));
      await tester.pump();
      expect(
        tester.widget<TextFormField>(find.byType(TextFormField)).enabled,
        false,
      );
      expect(healthRequests.single.url.host, 'health.example.com');
      expect(healthRequests.single.headers.containsKey('authorization'), false);
      health.complete(jsonResponse({'status': 'ok'}));
      await tester.pumpAndSettle();
      expect(find.textContaining('Connection successful'), findsOneWidget);
      await tester.enterText(
        find.widgetWithText(TextFormField, 'API origin'),
        'https://changed.example.com',
      );
      await tester.pump();
      expect(find.textContaining('Connection successful'), findsNothing);
      expect(session.origin!.value, 'https://example.com');
    },
  );

  testWidgets(
    'background clears entered password and resume conceals audits until revalidation',
    (tester) async {
      await pumpApp(tester);
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Password'),
        'secret',
      );
      for (final state in [
        AppLifecycleState.inactive,
        AppLifecycleState.hidden,
        AppLifecycleState.paused,
      ]) {
        tester.binding.handleAppLifecycleStateChanged(state);
      }
      await tester.pump();
      final fields = tester.widgetList<TextFormField>(
        find.byType(TextFormField, skipOffstage: false),
      );
      expect(fields.last.controller!.text, isEmpty);
      expect(find.text('Username'), findsNothing);
      for (final state in [
        AppLifecycleState.hidden,
        AppLifecycleState.inactive,
        AppLifecycleState.resumed,
      ]) {
        tester.binding.handleAppLifecycleStateChanged(state);
      }
      await tester.pumpAndSettle();
      await login(tester);
      final verified = Completer<http.StreamedResponse>();
      customRead = (_) => verified.future;
      for (final state in [
        AppLifecycleState.inactive,
        AppLifecycleState.hidden,
        AppLifecycleState.paused,
      ]) {
        tester.binding.handleAppLifecycleStateChanged(state);
      }
      await tester.pump();
      expect(find.text('Driver Audits'), findsNothing);
      for (final state in [
        AppLifecycleState.hidden,
        AppLifecycleState.inactive,
        AppLifecycleState.resumed,
      ]) {
        tester.binding.handleAppLifecycleStateChanged(state);
      }
      await tester.pump();
      expect(find.text('Driver Audits'), findsNothing);
      verified.complete(jsonResponse(userJson()));
      await tester.pumpAndSettle();
      expect(find.text('Driver Audits'), findsOneWidget);
    },
  );

  testWidgets(
    '320dp 200 percent text remains scrollable in light and dark themes',
    (tester) async {
      tester.view.physicalSize = const Size(320, 800);
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      for (final theme in [ThemeChoice.light, ThemeChoice.dark]) {
        await pumpApp(tester, theme: theme);
        await login(tester);
        expect(tester.takeException(), isNull);
        await tester.scrollUntilVisible(
          find.text('José 🚚'),
          200,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.ensureVisible(find.text('José 🚚'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('José 🚚').first);
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        await tester.scrollUntilVisible(
          find.text('Original Snapshot'),
          200,
          scrollable: find.byType(Scrollable).first,
        );
        expect(find.text('Original Snapshot'), findsOneWidget);
        await session.signOut();
        await tester.pumpAndSettle();
        await tester.pumpWidget(const SizedBox());
      }
    },
  );
}
