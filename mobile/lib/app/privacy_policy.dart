import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../features/auth/session_controller.dart';

bool allowFictionalCapture({
  required bool debugBuild,
  required bool requested,
  required String? origin,
}) {
  if (!debugBuild || !requested || origin == null) return false;
  final uri = Uri.tryParse(origin);
  return uri != null &&
      uri.scheme == 'http' &&
      uri.hasPort &&
      const ['127.0.0.1', 'localhost'].contains(uri.host) &&
      uri.userInfo.isEmpty &&
      (uri.path.isEmpty || uri.path == '/') &&
      !uri.hasQuery &&
      !uri.hasFragment;
}

/// Native windows start secure. This can relax capture only for deliberate
/// debug/loopback fictional acceptance; it never changes authentication or TLS.
class NativePrivacyGuard {
  NativePrivacyGuard(this.session, {required this.requested}) {
    session.addListener(_update);
    _update();
  }
  final SessionController session;
  final bool requested;
  static const _channel = MethodChannel('com.bhli.audit/privacy');

  void _update() {
    final capture = allowFictionalCapture(
      debugBuild: kDebugMode,
      requested: requested,
      origin: session.origin?.value,
    );
    _setSecure(!capture);
  }

  Future<void> _setSecure(bool secure) async {
    try {
      await _channel.invokeMethod<void>('setSecure', {'secure': secure});
    } on MissingPluginException {
      // Non-Android widget tests have no native window. Android starts secure.
    } on PlatformException {
      // A failed relaxation leaves the native default secure.
    }
  }

  void dispose() => session.removeListener(_update);
}
