import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'app/bhli_audit_app.dart';
import 'app/privacy_policy.dart';
import 'core/network/api_client.dart';
import 'core/network/api_failure.dart';
import 'core/network/api_origin.dart';
import 'core/settings/public_settings.dart';
import 'features/auth/session_controller.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final store = PreferencesSettingsStore();
  var settings = const PublicSettings();
  String? notice;
  const captureMode =
      kDebugMode && bool.fromEnvironment('DAMS_FICTIONAL_CAPTURE');
  final session = SessionController((origin) {
    // A deliberately capturable acceptance build cannot authenticate to remote
    // services. Normal debug/release builds keep native window capture blocked.
    if (captureMode &&
        !allowFictionalCapture(
          debugBuild: kDebugMode,
          requested: true,
          origin: origin.value,
        )) {
      throw ApiFailure.invalidOrigin;
    }
    return ApiClient(origin);
  });
  const allowLoopback =
      kDebugMode && bool.fromEnvironment('DAMS_DEBUG_LOOPBACK');
  try {
    settings = await store.load();
    if (settings.origin != null) {
      session.setOrigin(
        ApiOrigin.parse(settings.origin!, allowDebugLoopback: allowLoopback),
      );
    }
  } catch (_) {
    settings = const PublicSettings();
    notice = 'Saved connection settings could not be read. Enter your approved API origin.';
  }
  if (captureMode) {
    // Session listener lasts for this process. Native release code independently
    // refuses capture relaxation for non-debuggable builds.
    NativePrivacyGuard(session, requested: true);
  }
  runApp(
    BhliAuditApp(
      session: session,
      settingsStore: store,
      initialSettings: settings,
      allowDebugLoopback: allowLoopback,
      startupNotice: notice,
    ),
  );
}
