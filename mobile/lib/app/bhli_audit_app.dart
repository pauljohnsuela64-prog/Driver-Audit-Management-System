import 'package:flutter/material.dart';

import '../core/settings/public_settings.dart';
import '../features/auth/session_controller.dart';
import '../features/auth/login_screen.dart';
import '../features/audits/audit_list_screen.dart';
import '../features/settings/settings_screen.dart';
import '../core/network/api_origin.dart';
import '../ui/core/audit_theme.dart';

class BhliAuditApp extends StatefulWidget {
  const BhliAuditApp({
    super.key,
    required this.session,
    required this.settingsStore,
    required this.initialSettings,
    this.allowDebugLoopback = false,
    this.startupNotice,
  });
  final SessionController session;
  final SettingsStore settingsStore;
  final PublicSettings initialSettings;
  final bool allowDebugLoopback;
  final String? startupNotice;

  @override
  State<BhliAuditApp> createState() => _BhliAuditAppState();
}

class _BhliAuditAppState extends State<BhliAuditApp>
    with WidgetsBindingObserver {
  late PublicSettings _settings;
  bool _concealed = false;
  bool _requiresIdentityVerification = false;
  int _lifecycleRequest = 0;

  @override
  void initState() {
    super.initState();
    _settings = widget.initialSettings;
    WidgetsBinding.instance.addObserver(this);
    widget.session.addListener(_changed);
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _lifecycleRequest++;
    WidgetsBinding.instance.removeObserver(this);
    widget.session.removeListener(_changed);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) {
      _lifecycleRequest++;
      // A rapid app switch may resume from inactive without reaching paused.
      // Never reveal cached authorization/data without the shared identity check.
      _requiresIdentityVerification = true;
      setState(() {
        _concealed = true;
      });
    } else {
      _resume();
    }
  }

  Future<void> _resume() async {
    final request = ++_lifecycleRequest;
    if (_requiresIdentityVerification && widget.session.user != null) {
      await widget.session.verifyOnResume();
    }
    if (!mounted || request != _lifecycleRequest) return;
    setState(() {
      _concealed = false;
      _requiresIdentityVerification = false;
    });
  }

  Future<void> _saveOrigin(ApiOrigin origin) async {
    final settings = PublicSettings(
      origin: origin.value,
      theme: _settings.theme,
    );
    await widget.settingsStore.save(settings);
    if (!mounted) return;
    widget.session.setOrigin(origin);
    setState(() {
      _settings = settings;
    });
  }

  Future<void> _saveTheme(ThemeChoice theme) async {
    final settings = PublicSettings(
      origin: widget.session.origin?.value,
      theme: theme,
    );
    await widget.settingsStore.save(settings);
    if (mounted) {
      setState(() {
        _settings = settings;
      });
    }
  }

  Widget _settingsScreen({bool firstLaunch = false}) => SettingsScreen(
    session: widget.session,
    theme: _settings.theme,
    onSaveOrigin: _saveOrigin,
    onTheme: _saveTheme,
    firstLaunch: firstLaunch,
    startupNotice: firstLaunch ? widget.startupNotice : null,
    allowDebugLoopback: widget.allowDebugLoopback,
  );

  void _openSettings(BuildContext context) =>
      Navigator.of(context)
          .push(MaterialPageRoute<void>(builder: (_) => _settingsScreen()));

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    return MaterialApp(
      title: 'BHLI Audit',
      debugShowCheckedModeBanner: false,
      theme: auditTheme(Brightness.light),
      darkTheme: auditTheme(Brightness.dark),
      themeMode: switch (_settings.theme) {
        ThemeChoice.system => ThemeMode.system,
        ThemeChoice.light => ThemeMode.light,
        ThemeChoice.dark => ThemeMode.dark,
      },
      home: Stack(
        children: [
          Offstage(
            offstage: _concealed,
            child: _SessionRoutes(
              key: ValueKey(
                session.user == null
                    ? 'signed-out:${session.origin?.value}'
                    : '${session.generation}:${session.user!.id}',
              ),
              rootBuilder: (context) {
                if (session.origin == null) {
                  return _settingsScreen(firstLaunch: true);
                }
                if (session.user == null) {
                  return LoginScreen(
                    session: session,
                    onSettings: () => _openSettings(context),
                  );
                }
                return AuditListScreen(
                  session: session,
                  onSettings: () => _openSettings(context),
                );
              },
            ),
          ),
          if (_concealed)
            Positioned.fill(
              child: ColoredBox(
                color: const Color(0xff0b1220),
                child: Center(
                  child: Semantics(
                    liveRegion: true,
                    child: const Text(
                      'BHLI Audit',
                      style: TextStyle(color: Colors.white, fontSize: 24),
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

// A fresh protected scope clears the route stack; the inner Navigator handles
// Android Back while its root preserves normal app exit behavior.
class _SessionRoutes extends StatefulWidget {
  const _SessionRoutes({super.key, required this.rootBuilder});
  final WidgetBuilder rootBuilder;

  @override
  State<_SessionRoutes> createState() => _SessionRoutesState();
}

class _SessionRoutesState extends State<_SessionRoutes> {
  final _navigator = GlobalKey<NavigatorState>();

  @override
  Widget build(BuildContext context) => NavigatorPopHandler<void>(
    // Respect route PopScope guards (dirty drafts and pending mutations).
    // A direct pop would discard a form without invoking its confirmation.
    onPopWithResult: (_) => _navigator.currentState!.maybePop(),
    child: Navigator(
      key: _navigator,
      onGenerateRoute: (_) =>
          MaterialPageRoute<void>(builder: widget.rootBuilder),
    ),
  );
}
