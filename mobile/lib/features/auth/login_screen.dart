import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../ui/core/content.dart';
import 'session_controller.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    required this.session,
    required this.onSettings,
  });
  final SessionController session;
  final VoidCallback onSettings;
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> with WidgetsBindingObserver {
  final _form = GlobalKey<FormState>();
  final _username = TextEditingController();
  final _password = TextEditingController();
  final _passwordFocus = FocusNode();
  bool _obscured = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    widget.session.addListener(_changed);
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) {
      _password.clear();
      if (widget.session.busy) widget.session.cancelSignIn();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    widget.session.removeListener(_changed);
    _password.clear();
    _password.dispose();
    _username.dispose();
    _passwordFocus.dispose();
    super.dispose();
  }

  Future<void> _signIn() async {
    if (widget.session.busy || !_form.currentState!.validate()) return;
    FocusScope.of(context).unfocus();
    try {
      await widget.session.signIn(_username.text.trim(), _password.text);
    } finally {
      if (mounted) _password.clear();
      TextInput.finishAutofillContext(shouldSave: false);
    }
  }

  void _settings() {
    _password.clear();
    widget.onSettings();
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    return Scaffold(
      appBar: AppBar(title: const Text('BHLI Audit')),
      body: SafeArea(
        child: ContentWidth(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: AutofillGroup(
              child: Form(
                key: _form,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Semantics(
                      label: 'BHLI',
                      child: CircleAvatar(
                        radius: 32,
                        backgroundColor: Theme.of(context).colorScheme.primary,
                        child: Text(
                          'BH',
                          style: TextStyle(
                            fontSize: 24,
                            color: Theme.of(context).colorScheme.onPrimary,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),
                    Text(
                      'Sign in to view driver audits',
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 24),
                    TextFormField(
                      controller: _username,
                      enabled: !session.busy,
                      decoration: const InputDecoration(labelText: 'Username'),
                      autofillHints: const [AutofillHints.username],
                      autocorrect: false,
                      textInputAction: TextInputAction.next,
                      onFieldSubmitted: (_) => _passwordFocus.requestFocus(),
                      validator: (value) =>
                          value == null ||
                              value.trim().isEmpty ||
                              value.trim().runes.length > 100
                          ? 'Enter a username of 1–100 characters.'
                          : null,
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      controller: _password,
                      focusNode: _passwordFocus,
                      enabled: !session.busy,
                      obscureText: _obscured,
                      autofillHints: const [AutofillHints.password],
                      autocorrect: false,
                      enableSuggestions: false,
                      textInputAction: TextInputAction.done,
                      decoration: InputDecoration(
                        labelText: 'Password',
                        suffixIcon: IconButton(
                          tooltip: _obscured
                              ? 'Show password'
                              : 'Hide password',
                          onPressed: () => setState(() {
                            _obscured = !_obscured;
                          }),
                          icon: Icon(
                            _obscured
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                        ),
                      ),
                      onFieldSubmitted: (_) => _signIn(),
                      validator: (value) =>
                          value == null ||
                              value.isEmpty ||
                              value.runes.length > 128
                          ? 'Enter your password (1–128 characters).'
                          : null,
                    ),
                    const SizedBox(height: 24),
                    FilledButton(
                      onPressed: session.busy ? null : _signIn,
                      child: const Text('Sign in'),
                    ),
                    if (session.busy)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 16),
                        child: LinearProgressIndicator(
                          semanticsLabel: 'Signing in',
                        ),
                      ),
                    if (session.notice case final notice?)
                      StatusMessage(notice, error: true),
                    const SizedBox(height: 24),
                    Text('Connected to: ${session.origin!.value}'),
                    TextButton(
                      onPressed: session.canChangeOrigin ? _settings : null,
                      child: const Text('Connection settings'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
