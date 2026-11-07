import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../ui/core/content.dart';
import 'backup_crypto.dart';
import 'backup_documents.dart';
import 'backup_evidence.dart';
import 'backup_state.dart';
import 'backup_store.dart';

/// Controllers are cleared before handing the passphrase to a single operation.
class BackupPassphraseForm extends StatefulWidget {
  const BackupPassphraseForm({super.key, this.onSubmit, this.confirm = true});
  final ValueChanged<String>? onSubmit;
  final bool confirm;
  @override
  State<BackupPassphraseForm> createState() => _BackupPassphraseFormState();
}

class _BackupPassphraseFormState extends State<BackupPassphraseForm> {
  final form = GlobalKey<FormState>();
  final password = TextEditingController();
  final confirmation = TextEditingController();
  bool visible = false;
  String? validatePassword(String? value) {
    final text = value ?? '';
    if (text.runes.length < 15 || text.runes.length > 128) {
      return 'Use 15 to 128 characters.';
    }
    for (var i = 0; i < text.length; i++) {
      final code = text.codeUnitAt(i);
      if (code < 32 || (code >= 127 && code <= 159)) {
        return 'Use characters without control codes.';
      }
      if (code >= 0xd800 && code <= 0xdbff) {
        if (++i >= text.length ||
            text.codeUnitAt(i) < 0xdc00 ||
            text.codeUnitAt(i) > 0xdfff) {
          return 'Use valid Unicode characters.';
        }
      } else if (code >= 0xdc00 && code <= 0xdfff) {
        return 'Use valid Unicode characters.';
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    child: Form(
      key: form,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'Use a unique passphrase of 15 to 128 characters. Spaces are significant. A lost passphrase cannot be reset. Keep it separately from your backup.',
          ),
          const SizedBox(height: 16),
          TextFormField(
            key: const ValueKey('backup_password'),
            controller: password,
            obscureText: !visible,
            autocorrect: false,
            enableSuggestions: false,
            decoration: const InputDecoration(
              labelText: 'Backup passphrase',
              errorMaxLines: 4,
            ),
            validator: validatePassword,
          ),
          if (widget.confirm) ...[
            const SizedBox(height: 16),
            TextFormField(
              key: const ValueKey('backup_confirmation'),
              controller: confirmation,
              obscureText: !visible,
              autocorrect: false,
              enableSuggestions: false,
              decoration: const InputDecoration(
                labelText: 'Confirm passphrase',
                errorMaxLines: 4,
              ),
              validator: (value) => value != password.text
                  ? 'The passphrases must match exactly.'
                  : null,
            ),
          ],
          TextButton.icon(
            onPressed: () => setState(() => visible = !visible),
            icon: Icon(visible ? Icons.visibility_off : Icons.visibility),
            label: Text(visible ? 'Hide passphrase' : 'Show passphrase'),
          ),
          FilledButton(
            onPressed: () {
              if (!form.currentState!.validate()) return;
              final value = password.text;
              password.clear();
              confirmation.clear();
              widget.onSubmit?.call(value);
            },
            child: const Text('Continue'),
          ),
        ],
      ),
    ),
  );
  @override
  void dispose() {
    password.clear();
    confirmation.clear();
    password.dispose();
    confirmation.dispose();
    super.dispose();
  }
}

class OfflineBackupScreen extends StatefulWidget {
  const OfflineBackupScreen({
    super.key,
    required this.store,
    required this.onRestored,
    this.documents,
    this.evidence,
  });
  final BackupStore store;
  final ValueChanged<String> onRestored;
  final BackupDocuments? documents;
  final BackupEvidence? evidence;
  @override
  State<OfflineBackupScreen> createState() => _OfflineBackupScreenState();
}

class _OfflineBackupScreenState extends State<OfflineBackupScreen>
    with WidgetsBindingObserver {
  late final documents = widget.documents ?? NativeBackupDocuments();
  late final evidence = widget.evidence ?? NativeBackupEvidence();
  String mode = 'home';
  String? message;
  bool busy = false, cancelled = false, acknowledged = false, blocked = false;
  RestorePreview? preview;
  PreparedRestore? ticket;
  String? selectedInput;
  bool confirming = false;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.paused &&
        state != AppLifecycleState.detached) {
      return;
    }
    // Android's system document picker legitimately pauses this Activity.
    // Its pending result remains owned; only an applying ticket requests stop.
    if (busy) {
      if (ticket != null) unawaited(cancel());
      return;
    }
    if (confirming) Navigator.pop(context, false);
    if (ticket != null) {
      unawaited(
        run(() async {
          await widget.store.cancelPrepared(ticket!);
          ticket = null;
          if (mounted) {
            setState(() {
              preview = null;
              mode = 'home';
              message = 'Prepared replacement cancelled when the app left the foreground. Inspect a fresh backup to continue.';
            });
          }
        }),
      );
    } else if (preview != null) {
      widget.store.cancelPreview(preview!);
      setState(() {
        preview = null;
        mode = 'home';
      });
    } else if (mode != 'home') {
      // Rebuilding disposes passphrase controllers rather than retaining secrets
      // in an unattended background form.
      setState(() => mode = 'home');
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    cancelled = true;
    if (ticket != null) widget.store.requestCancel(ticket!);
    if (preview != null) widget.store.cancelPreview(preview!);
    super.dispose();
  }

  Future<void> run(Future<void> Function() operation) async {
    if (busy || blocked) return;
    setState(() {
      busy = true;
      cancelled = false;
      message = null;
    });
    try {
      await operation();
    } catch (error) {
      if (mounted) {
        setState(() {
          // Never print provider errors, paths, file contents or passphrases.
          if (ticket != null) blocked = true;
          message = ticket != null
              ? assistedAndroidRecovery
              : error is PlatformException && error.code == 'cleanup_incomplete'
              ? 'The incomplete newly created document could not be removed. Remove that incomplete output manually before trying again. Keep existing backups. Nothing is confirmed restored.'
              : cancelled
              ? 'Operation stopped. Encrypted recovery files may have been retained. No replacement was requested.'
              : error is BackupStoreFailure
              ? error.message
              : error is BackupFailure
              ? error.message
              : 'The backup operation could not be verified. Keep all encrypted files and try again. Nothing is confirmed restored.';
          if (mode == 'recovery' && ticket == null) {
            preview = null;
            selectedInput = null;
            mode = 'home';
          }
        });
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<Uint8List> save(BackupArtifact artifact, String name) async {
    if (cancelled) {
      throw const BackupStoreFailure(
        'cancelled',
        'Cancelled before replacement.',
      );
    }
    final handle = await documents.saveBackup(artifact.handle, name);
    if (handle == null) {
      throw const BackupStoreFailure(
        'cancelled',
        'No destination was saved. Nothing was replaced.',
      );
    }
    return evidence.read(handle);
  }

  Future<void> submit(String password) => run(() async {
    try {
      if (mode == 'create') {
        final artifact = await widget.store.createBackup(
          password,
          cancel: () => cancelled,
        );
        final saved = await save(artifact, 'BHLI-backup.bhlibackup');
        if (!listEquals(saved, artifact.bytes)) throw const FormatException();
        await openBackup(saved, password, platform: 'android');
        if (mounted) {
          setState(() {
            mode = 'home';
            message =
                'Encrypted complete backup saved and authenticated from destination readback at your selected destination. '
                'Created: ${artifact.state.metadata['created_at']}. '
                'Audits: ${artifact.state.rows['audit_records']!.length}; history: ${artifact.state.rows['audit_events']!.length}; transfer receipts: ${artifact.state.rows['transfer_receipts']!.length}. '
                'Keep another copy off this device; a same-device copy is not disaster recovery.';
          });
        }
      } else if (mode == 'restore') {
        final candidate = await widget.store.inspectRestore(
          await evidence.read(selectedInput!),
          password,
          cancel: () => cancelled,
        );
        if (!mounted || cancelled) {
          widget.store.cancelPreview(candidate);
          return;
        }
        setState(() {
          preview = candidate;
          mode = 'preview';
          message = candidate.unchanged
              ? 'The authenticated backup already matches this device. No replacement is needed.'
              : null;
        });
      } else if (mode == 'recovery') {
        final prepared = await widget.store.prepareRestore(
          preview!,
          password,
          publishRecovery: (artifact) =>
              save(artifact, 'BHLI-before-restore.bhlibackup'),
          cancel: () => cancelled,
        );
        if (!mounted || cancelled) {
          await widget.store.cancelPrepared(prepared);
          return;
        }
        setState(() {
          ticket = prepared;
          mode = 'prepared';
          acknowledged = false;
        });
      }
    } finally {
      password = '';
    }
  });

  Future<void> cancel() async {
    cancelled = true;
    final prepared = ticket;
    if (busy) {
      if (prepared != null) widget.store.requestCancel(prepared);
      if (mounted) {
        setState(
          () => message = prepared == null
              ? 'Cancellation requested. Waiting for the operation to stop.'
              : 'Cancellation requested. Waiting for the verified restore outcome; it may already have committed.',
        );
      }
      try {
        await documents.cancel();
      } catch (_) {
        /* Await the operation's classified result. */
      }
      return;
    }
    if (prepared != null) {
      setState(() => busy = true);
      try {
        await widget.store.cancelPrepared(prepared);
      } catch (_) {
        if (mounted) {
          setState(() {
            blocked = true;
            message = assistedAndroidRecovery;
          });
        }
        return;
      } finally {
        if (mounted) setState(() => busy = false);
      }
      ticket = null;
    }
    if (preview != null) widget.store.cancelPreview(preview!);
    if (mounted) Navigator.pop(context);
  }

  Future<void> replace() async {
    if (!acknowledged || busy || ticket == null) return;
    confirming = true;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        scrollable: true,
        title: const Text("Replace this device's data?"),
        content: const SingleChildScrollView(
          child: Text(
            'This replaces all local audits, history, receipts, profile and installation identity with the authenticated backup. Retire duplicate active identities. Your verified recovery backup protects the current state.',
          ),
        ),
        actions: [
          TextButton(
            autofocus: true,
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text("Replace this device's data"),
          ),
        ],
      ),
    );
    confirming = false;
    if (!mounted || busy || ticket == null) return;
    if (confirmed != true) {
      await run(() async {
        await widget.store.cancelPrepared(ticket!);
        ticket = null;
        if (mounted) {
          setState(() {
            preview = null;
            mode = 'home';
            message = 'Replacement cancelled. The complete original state is unchanged.';
          });
        }
      });
      return;
    }
    await run(() async {
      final result = await widget.store.applyRestore(ticket!);
      ticket = null;
      if (!mounted) return;
      if (result.outcome == RestoreOutcome.restored) {
        widget.onRestored(result.warning);
        return;
      }
      setState(() {
        blocked =
            result.outcome == RestoreOutcome.unknown ||
            result.warning.isNotEmpty;
        mode = 'home';
        message = result.outcome == RestoreOutcome.original
            ? 'The complete original state was verified. Nothing was replaced. ${result.warning}'
            : assistedAndroidRecovery;
      });
    });
  }

  Widget summary(String label, BackupState state) {
    final profile = state.rows['local_profile']!;
    final installation = state.rows['app_meta']!
        .where((r) => r['key'] == 'installation_id')
        .single['value'];
    final records = state.rows['audit_records']!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(label, style: Theme.of(context).textTheme.titleMedium),
        Text(
          profile.isEmpty
              ? 'Profile: none (empty setup)'
              : 'Profile: ${profile.single['name']} (${profile.single['id']})',
        ),
        Text('Installation: $installation'),
        Text(
          'Audits: ${records.length}; active: ${records.where((r) => r['archived_at'] == null).length}; archived: ${records.where((r) => r['archived_at'] != null).length}',
        ),
        Text(
          'History: ${state.rows['audit_events']!.length}; transfer receipts: ${state.rows['transfer_receipts']!.length}; auditor identities: ${state.rows['auditor_identities']!.length}',
        ),
        const SizedBox(height: 16),
      ],
    );
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !busy && ticket == null && !blocked,
    onPopInvokedWithResult: (didPop, _) {
      if (!didPop && !blocked) unawaited(cancel());
    },
    child: Scaffold(
      appBar: AppBar(
        title: const Text('Backup & restore'),
        automaticallyImplyLeading: !blocked,
        leading: blocked ? null : BackButton(onPressed: cancel),
      ),
      body: SafeArea(
        child: ContentWidth(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'Complete encrypted Android backups include all audits, archived audits, history, transfer receipts, profile and installation identity. List filters do not limit a backup. Restore replaces the entire local state. Close or discard unfinished drafts before continuing.',
                ),
                const SizedBox(height: 16),
                if (message != null)
                  Semantics(liveRegion: true, child: Text(message!)),
                if (busy) ...[
                  const LinearProgressIndicator(),
                  const Text(
                    'Working locally. Keep this screen open until the verified outcome is shown.',
                  ),
                  OutlinedButton(
                    onPressed: cancel,
                    child: const Text('Cancel operation'),
                  ),
                ] else if (!blocked) ...[
                  if (mode == 'home') ...[
                    FilledButton(
                      onPressed: () => setState(() => mode = 'create'),
                      child: const Text('Create Backup'),
                    ),
                    OutlinedButton(
                      onPressed: () => run(() async {
                        final handle = await documents.pickBackup();
                        if (handle != null && !cancelled && mounted) {
                          setState(() {
                            selectedInput = handle;
                            mode = 'restore';
                          });
                        }
                      }),
                      child: const Text('Restore Backup'),
                    ),
                  ],
                  if (mode == 'create' ||
                      mode == 'restore' ||
                      mode == 'recovery') ...[
                    if (mode == 'recovery')
                      const Text(
                        'Re-enter the incoming backup passphrase. A complete encrypted recovery backup of the current state must be saved to a new destination and authenticated from actual readback before replacement can be confirmed.',
                      ),
                    BackupPassphraseForm(
                      key: ValueKey(mode),
                      onSubmit: submit,
                      confirm: mode != 'restore',
                    ),
                  ],
                  if ((mode == 'preview' || mode == 'prepared') &&
                      preview != null) ...[
                    const Text('Authenticated replacement preview'),
                    summary('Current device', preview!.current),
                    summary('Incoming backup', preview!.candidate),
                    Text(
                      'Backup created: ${preview!.candidate.metadata['created_at']}',
                    ),
                    const Text(
                      'The backup restores its installation identity. Do not keep two active copies using that identity.',
                    ),
                    if (mode == 'preview' && !preview!.unchanged)
                      FilledButton(
                        onPressed: () => setState(() => mode = 'recovery'),
                        child: const Text('Save required recovery backup'),
                      ),
                    if (mode == 'prepared') ...[
                      const Text(
                        'Recovery backup saved and authenticated from destination readback.',
                      ),
                      CheckboxListTile(
                        contentPadding: EdgeInsets.zero,
                        value: acknowledged,
                        onChanged: (value) =>
                            setState(() => acknowledged = value == true),
                        title: const Text(
                          'I understand this replaces all audits, history, receipts, profile and installation identity. I will retire duplicate active identities.',
                        ),
                      ),
                      FilledButton(
                        onPressed: acknowledged ? replace : null,
                        child: const Text("Replace this device's data"),
                      ),
                    ],
                  ],
                ],
              ],
            ),
          ),
        ),
      ),
    ),
  );
}
