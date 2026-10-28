import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import '../../core/network/api_failure.dart';
import '../../core/network/api_origin.dart';
import '../../core/settings/public_settings.dart';
import '../../ui/core/content.dart';
import '../auth/session_controller.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    super.key,
    required this.session,
    required this.theme,
    required this.onSaveOrigin,
    required this.onTheme,
    this.firstLaunch = false,
    this.allowDebugLoopback = false,
    this.healthClientFactory,
    this.startupNotice,
  });
  final SessionController session;
  final ThemeChoice theme;
  final Future<void> Function(ApiOrigin) onSaveOrigin;
  final Future<void> Function(ThemeChoice) onTheme;
  final bool firstLaunch;
  final bool allowDebugLoopback;
  final ApiClient Function(ApiOrigin)? healthClientFactory;
  final String? startupNotice;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _origin;
  String? _message;
  bool _error = false;
  bool _testing = false;
  bool _saving = false;
  int _healthRequest = 0;
  ApiClient? _healthClient;

  @override
  void initState() {
    super.initState();
    _origin = TextEditingController(text: widget.session.origin?.value ?? '');
    widget.session.addListener(_changed);
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _healthRequest++;
    _healthClient?.cancelAll();
    widget.session.removeListener(_changed);
    _origin.dispose();
    super.dispose();
  }

  ApiOrigin _candidate() => ApiOrigin.parse(
    _origin.text,
    allowDebugLoopback: widget.allowDebugLoopback,
  );

  Future<void> _test() async {
    final request = ++_healthRequest;
    setState(() {
      _testing = true;
      _message = null;
    });
    try {
      final candidate = _candidate();
      final client = (widget.healthClientFactory ?? ApiClient.new)(candidate);
      _healthClient = client;
      await client.health();
      if (!mounted || request != _healthRequest) return;
      setState(() {
        _error = false;
        _message = 'Connection successful. Basic API health confirmed.';
      });
    } on ApiFailure catch (failure) {
      if (mounted && request == _healthRequest) {
        setState(() {
          _error = true;
          _message = failure.message;
        });
      }
    } catch (_) {
      if (mounted && request == _healthRequest) {
        setState(() {
          _error = true;
          _message = 'Unable to test this connection.';
        });
      }
    } finally {
      _healthClient?.cancelAll();
      if (mounted && request == _healthRequest) {
        setState(() {
          _testing = false;
        });
      }
    }
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _message = null;
    });
    try {
      await widget.onSaveOrigin(_candidate());
      if (mounted && !widget.firstLaunch) Navigator.of(context).pop();
    } on ApiFailure catch (failure) {
      if (mounted) {
        setState(() {
          _error = true;
          _message = failure.message;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _error = true;
          _message =
              'Unable to save connection. Previous settings remain active.';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _saving = false;
        });
      }
    }
  }

  Future<void> _theme(ThemeChoice? choice) async {
    if (choice == null) return;
    setState(() {
      _saving = true;
      _message = null;
    });
    try {
      await widget.onTheme(choice);
    } catch (_) {
      if (mounted) {
        setState(() {
          _error = true;
          _message = 'Unable to save appearance.';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _saving = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    final locked = !session.canChangeOrigin;
    final waiting = _testing || _saving || session.busy;
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.firstLaunch ? 'Connection setup' : 'Settings'),
      ),
      body: SafeArea(
        child: ContentWidth(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (widget.startupNotice case final notice?)
                StatusMessage(notice, error: true),
              if (session.user case final user?) ...[
                Text(
                  user.fullName,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                Text('${user.username} · ${user.role}'),
                const SizedBox(height: 24),
              ],
              Text(
                'API connection',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 16),
              if (locked) ...[
                SelectableText(
                  session.origin?.value ?? 'No connection configured',
                ),
                const Text('Sign out before changing the connection.'),
              ] else ...[
                TextFormField(
                  controller: _origin,
                  enabled: !waiting,
                  keyboardType: TextInputType.url,
                  autocorrect: false,
                  textInputAction: TextInputAction.done,
                  decoration: const InputDecoration(
                    labelText: 'API origin',
                    hintText: 'https://audit.example.com',
                  ),
                  onChanged: (_) {
                    _healthRequest++;
                    setState(() {
                      _message = null;
                    });
                  },
                ),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: [
                    OutlinedButton(
                      onPressed: waiting ? null : _test,
                      child: const Text('Test connection'),
                    ),
                    FilledButton(
                      onPressed: waiting ? null : _save,
                      child: const Text('Save connection'),
                    ),
                  ],
                ),
              ],
              if (waiting)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16),
                  child: LinearProgressIndicator(semanticsLabel: 'Working'),
                ),
              if (_message case final message?)
                StatusMessage(message, error: _error),
              const SizedBox(height: 24),
              DropdownButtonFormField<ThemeChoice>(
                initialValue: widget.theme,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Appearance'),
                items: ThemeChoice.values
                    .map(
                      (choice) => DropdownMenuItem(
                        value: choice,
                        child: Text(switch (choice) {
                          ThemeChoice.system => 'System',
                          ThemeChoice.light => 'Light',
                          ThemeChoice.dark => 'Dark',
                        }),
                      ),
                    )
                    .toList(),
                onChanged: waiting ? null : _theme,
              ),
              if (session.user != null) ...[
                const SizedBox(height: 32),
                OutlinedButton(
                  onPressed: waiting ? null : session.signOut,
                  child: const Text('Sign out'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
