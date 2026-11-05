import 'package:flutter/material.dart';

import '../ui/core/content.dart';
import 'models.dart';
import 'repository.dart';

const offlineFieldLabels = {
  'driver_name': 'Driver Name',
  'helper_name': 'Helper Name (optional)',
  'audit_date': 'Audit Date',
  'station': 'Station',
  'plate_number': 'Plate Number',
  'remarks': 'Remarks (optional)',
  'audited_by_name': 'Audited By',
};

/// Only recognized error codes influence UI behavior; storage details stay local.
String offlineError(
  Object error, {
  String operation = 'complete this operation',
}) {
  if (error is OfflineFailure) {
    if (error.code == 'conflict') {
      return 'This audit changed. Discard your draft and reload before editing again.';
    }
    if (error.code == 'not_found') return 'This audit is no longer available.';
    if (error.code == 'schema') {
      return 'This local database needs a compatible app version. Your data has not been removed.';
    }
  }
  return 'Could not $operation. Please retry. Your local data has not been removed.';
}

class OfflineAuditForm extends StatefulWidget {
  const OfflineAuditForm({
    super.key,
    required this.repository,
    required this.profile,
    this.record,
  });
  final OfflineRepository repository;
  final LocalProfile profile;
  final LocalAudit? record;
  @override
  State<OfflineAuditForm> createState() => _OfflineAuditFormState();
}

class _OfflineAuditFormState extends State<OfflineAuditForm> {
  static final keys = offlineFieldLabels.keys
      .where((key) => key != 'audited_by_name')
      .toList();
  final formKey = GlobalKey<FormState>();
  late final Map<String, TextEditingController> fields;
  late final Map<String, FocusNode> focus;
  late final String createId;
  late Map<String, String> baseline;
  LocalAudit? record;
  AuditValues? frozen;
  bool busy = false;
  bool leaving = false;
  bool confirming = false;
  bool conflict = false;
  String? error;
  List<String> invalid = [];

  @override
  void initState() {
    super.initState();
    createId = newUuid();
    record = widget.record;
    final source = record?.values.toJson() ?? <String, Object?>{};
    baseline = {for (final key in keys) key: source[key] as String? ?? ''};
    fields = {
      for (final key in keys) key: TextEditingController(text: baseline[key]),
    };
    focus = {for (final key in keys) key: FocusNode()};
  }

  String? validate(String key, String? value) {
    final text = value ?? '';
    if (key == 'audit_date') {
      return validOfflineDate(text)
          ? null
          : 'Enter a valid date as YYYY-MM-DD (1000–9999).';
    }
    const limits = {
      'driver_name': 200,
      'helper_name': 200,
      'station': 150,
      'plate_number': 30,
      'remarks': 10000,
    };
    final optional = key == 'helper_name' || key == 'remarks';
    try {
      offlineText(text, limits[key]!, optional: optional);
      return null;
    } on OfflineFailure {
      return !optional && text.trim().isEmpty
          ? 'This field is required.'
          : 'Use ${limits[key]} characters or fewer.';
    }
  }

  bool get dirty => keys.any((key) => fields[key]!.text != baseline[key]);

  Future<void> leave() async {
    if (busy || leaving || confirming) return;
    if (dirty || frozen != null) {
      confirming = true;
      final discard = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          scrollable: true,
          title: const Text('Discard changes?'),
          content: Text(
            frozen != null
                ? 'The save may already have completed. Leaving discards this retry attempt, not any saved data. Check the audit list before creating again.'
                : 'Your unsaved changes will be discarded.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Keep editing'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Discard changes'),
            ),
          ],
        ),
      );
      confirming = false;
      if (!mounted || discard != true) return;
    }
    if (!mounted) return;
    setState(() => leaving = true);
    Navigator.pop(context);
  }

  Future<void> save() async {
    if (busy || conflict || record?.archived == true) return;
    if (frozen == null) {
      if (!formKey.currentState!.validate()) {
        setState(
          () => invalid = keys
              .where((key) => validate(key, fields[key]!.text) != null)
              .toList(),
        );
        focus[invalid.first]!.requestFocus();
        return;
      }
      frozen = AuditValues.fromJson({
        for (final key in keys) key: fields[key]!.text,
      });
    }
    setState(() {
      busy = true;
      error = null;
      invalid = [];
    });
    var saved = false;
    try {
      if (record == null) {
        await widget.repository.create(createId, frozen!);
      } else {
        await widget.repository.update(record!.id, record!.revision, frozen!);
      }
      saved = true;
    } catch (failure) {
      if (mounted) {
        setState(() {
          conflict = failure is OfflineFailure && failure.code == 'conflict';
          error = offlineError(failure, operation: 'confirm this save');
        });
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
    if (saved && mounted) {
      setState(() => leaving = true);
      Navigator.pop(context, true);
    }
  }

  Future<void> reload() async {
    if (busy || record == null) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final latest = await widget.repository.read(record!.id);
      if (!mounted) return;
      setState(() {
        record = latest;
        final values = latest.values.toJson();
        baseline = {for (final key in keys) key: values[key] as String? ?? ''};
        for (final key in keys) {
          fields[key]!.text = baseline[key]!;
        }
        frozen = null;
        conflict = false;
        invalid = [];
      });
    } catch (failure) {
      if (mounted) {
        setState(
          () => error = offlineError(failure, operation: 'reload this audit'),
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> pickDate() async {
    final raw = fields['audit_date']!.text;
    final date = await showDatePicker(
      context: context,
      initialDate: validOfflineDate(raw) ? DateTime.parse(raw) : DateTime.now(),
      firstDate: DateTime(1000),
      lastDate: DateTime(9999, 12, 31),
    );
    if (!mounted || busy || frozen != null || date == null) return;
    fields['audit_date']!.text =
        '${date.year.toString().padLeft(4, '0')}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final enabled = !busy && frozen == null && record?.archived != true;
    return PopScope(
      canPop: leaving,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) leave();
      },
      child: Scaffold(
        appBar: AppBar(
          title: Text(record == null ? 'Create Audit' : 'Edit Audit'),
          leading: IconButton(
            tooltip: 'Back',
            onPressed: busy ? null : leave,
            icon: const Icon(Icons.arrow_back),
          ),
        ),
        body: SafeArea(
          child: ContentWidth(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Form(
                key: formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text('Audited By'),
                    Text(record?.auditedByName ?? widget.profile.name),
                    Text(
                      record == null
                          ? 'Self-declared local profile. New audits capture the current profile name when saved.'
                          : 'Original self-declared auditor. This name cannot be edited.',
                    ),
                    const SizedBox(height: 24),
                    if (busy)
                      const StatusMessage(
                        'Saving locally. Keep this screen open until the operation finishes.',
                      ),
                    if (record?.archived == true)
                      const StatusMessage(
                        'This audit is archived and cannot be edited.',
                      ),
                    if (invalid.isNotEmpty)
                      Semantics(
                        liveRegion: true,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            const Text('Check these fields before saving:'),
                            for (final key in invalid)
                              TextButton(
                                onPressed: () => focus[key]!.requestFocus(),
                                child: Text(offlineFieldLabels[key]!),
                              ),
                          ],
                        ),
                      ),
                    for (final key in keys)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            ExcludeSemantics(
                              child: Text(offlineFieldLabels[key]!),
                            ),
                            const SizedBox(height: 8),
                            Semantics(
                              label: offlineFieldLabels[key],
                              child: TextFormField(
                                key: ValueKey('offline_$key'),
                                controller: fields[key],
                                focusNode: focus[key],
                                enabled: enabled,
                                decoration: InputDecoration(
                                  errorMaxLines: 4,
                                  helperText: key == 'audit_date'
                                      ? 'YYYY-MM-DD'
                                      : null,
                                  suffixIcon: key == 'audit_date'
                                      ? IconButton(
                                          tooltip: 'Choose audit date',
                                          onPressed: enabled ? pickDate : null,
                                          icon: const Icon(
                                            Icons.calendar_today,
                                          ),
                                        )
                                      : null,
                                ),
                                minLines: key == 'remarks' ? 3 : 1,
                                maxLines: key == 'remarks' ? null : 1,
                                keyboardType: key == 'remarks'
                                    ? TextInputType.multiline
                                    : TextInputType.text,
                                textInputAction: key == 'remarks'
                                    ? TextInputAction.newline
                                    : TextInputAction.next,
                                onFieldSubmitted: key == 'remarks'
                                    ? null
                                    : (_) => focus[keys[keys.indexOf(key) + 1]]!
                                          .requestFocus(),
                                validator: (value) => validate(key, value),
                              ),
                            ),
                          ],
                        ),
                      ),
                    if (error != null) StatusMessage(error!, error: true),
                    if (frozen != null && !busy && !conflict)
                      const StatusMessage(
                        'The save may already have completed. Retry keeps the same audit and unchanged values.',
                      ),
                    if (conflict)
                      OutlinedButton(
                        onPressed: busy ? null : reload,
                        child: const Text('Discard changes and reload'),
                      ),
                    Wrap(
                      spacing: 16,
                      runSpacing: 8,
                      children: [
                        FilledButton(
                          onPressed:
                              busy || conflict || record?.archived == true
                              ? null
                              : save,
                          child: Text(
                            busy
                                ? 'Saving…'
                                : frozen != null
                                ? 'Retry save'
                                : 'Save',
                          ),
                        ),
                        TextButton(
                          onPressed: busy ? null : leave,
                          child: const Text('Cancel'),
                        ),
                      ],
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

  @override
  void dispose() {
    for (final field in fields.values) {
      field.dispose();
    }
    for (final node in focus.values) {
      node.dispose();
    }
    super.dispose();
  }
}
