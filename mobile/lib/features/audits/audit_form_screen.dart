import 'package:flutter/material.dart';

import '../auth/session_controller.dart';
import 'audit_draft.dart';
import 'audit_form_controller.dart';
import 'models.dart';
export 'audit_form_controller.dart' show AuditFormResult;

class AuditFormScreen extends StatefulWidget {
  const AuditFormScreen({
    super.key,
    required this.session,
    this.record,
    this.pendingCreate,
  });
  final SessionController session;
  final AuditRecord? record;
  final PendingAuditCreate? pendingCreate;
  @override
  State<AuditFormScreen> createState() => _AuditFormScreenState();
}

class _AuditFormScreenState extends State<AuditFormScreen> {
  static const labels = {
    'driver_name': 'Driver Name',
    'helper_name': 'Helper Name (optional)',
    'audit_date': 'Audit Date',
    'station': 'Station',
    'plate_number': 'Plate Number',
    'remarks': 'Remarks (optional)',
  };
  final formKey = GlobalKey<FormState>();
  late final AuditFormController form;
  late final Map<String, TextEditingController> fields;
  late final Map<String, FocusNode> focus;
  bool leaving = false;
  bool confirmingLeave = false;
  List<String> invalidFields = [];
  @override
  void initState() {
    super.initState();
    form = AuditFormController(
      session: widget.session,
      record: widget.record,
      pendingCreate: widget.pendingCreate,
    );
    fields = {
      for (final key in labels.keys)
        key: TextEditingController(text: form.values[key] as String? ?? ''),
    };
    focus = {for (final key in labels.keys) key: FocusNode()};
    form.addListener(changed);
  }

  void changed() {
    if (!mounted) return;
    if (!form.active) {
      for (final field in fields.values) {
        field.clear();
      }
    }
    setState(() {});
  }

  Future<void> leave({bool systemBack = false}) async {
    if (leaving || confirmingLeave) return;
    if (systemBack && MediaQuery.viewInsetsOf(context).bottom > 0) {
      FocusManager.instance.primaryFocus?.unfocus();
      return;
    }
    final uncertain = form.frozen || form.busy || form.requiresReload;
    if (form.active && (form.dirty || uncertain)) {
      confirmingLeave = true;
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          scrollable: true,
          title: Text(
            uncertain ? 'Leave this save attempt?' : 'Discard changes?',
          ),
          content: Text(
            uncertain
                ? widget.record == null
                      ? 'The server may already have saved this audit. The pending create attempt stays available for retry during this session.'
                      : 'The server may already have saved these changes. Close and reload this audit to check its current state.'
                : 'Your unsaved changes will be discarded.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Keep editing'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Leave'),
            ),
          ],
        ),
      );
      confirmingLeave = false;
      if (confirmed != true || !mounted || !form.active) return;
    }
    if (!mounted) return;
    if (form.active && form.busy) widget.session.cancelAuditMutation();
    setState(() => leaving = true);
    Navigator.pop(context);
  }

  Future<void> save() async {
    if (!form.canSave) return;
    if (!form.frozen && !formKey.currentState!.validate()) {
      setState(() {
        invalidFields = labels.keys
            .where((key) => form.validateField(key, fields[key]!.text) != null)
            .toList();
      });
      for (final key in labels.keys) {
        if (form.validateField(key, fields[key]!.text) != null) {
          focus[key]!.requestFocus();
          break;
        }
      }
      return;
    }
    final result = await form.save();
    if (!mounted) return;
    if (form.accessLost) {
      if (confirmingLeave) {
        Navigator.of(context, rootNavigator: true).pop(false);
      }
      setState(() => leaving = true);
      Navigator.pop(context);
      return;
    }
    if (!form.active || result == null) return;
    if (confirmingLeave) {
      Navigator.of(context, rootNavigator: true).pop(false);
    }
    setState(() => leaving = true);
    Navigator.pop(context, result);
  }

  Future<void> pickDate() async {
    final parsed = DateTime.tryParse(fields['audit_date']!.text);
    final now = DateTime.now();
    final date = await showDatePicker(
      context: context,
      initialDate: parsed != null && parsed.year >= 1000 && parsed.year <= 9999
          ? parsed
          : now,
      firstDate: DateTime(1000),
      lastDate: DateTime(9999, 12, 31),
    );
    if (!mounted || !form.active || form.frozen || date == null) return;
    final value =
        '${date.year.toString().padLeft(4, '0')}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
    fields['audit_date']!.text = value;
    form.values['audit_date'] = value;
    setState(() {});
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: leaving,
    onPopInvokedWithResult: (didPop, result) {
      if (!didPop) leave(systemBack: true);
    },
    child: Scaffold(
      appBar: AppBar(
        title: Text(widget.record == null ? 'Create Audit' : 'Edit Audit'),
        leading: IconButton(
          tooltip: 'Back',
          onPressed: leave,
          icon: const Icon(Icons.arrow_back),
        ),
      ),
      body: SafeArea(
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Form(
                key: formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text('Audited By'),
                    Text(
                      form.active
                          ? widget.record?.auditedByName ??
                                widget.session.user?.fullName ??
                                ''
                          : '',
                    ),
                    if (widget.record == null)
                      const Text(
                        'The server assigns Audited By to the signed-in account.',
                      ),
                    if (widget.record == null)
                      const Text(
                        'If a previous save was interrupted, check Audits before creating again.',
                      ),
                    const SizedBox(height: 24),
                    if (invalidFields.isNotEmpty && form.active)
                      Semantics(
                        liveRegion: true,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            const Text('Check these fields before saving:'),
                            for (final key in invalidFields)
                              TextButton(
                                onPressed: () => focus[key]!.requestFocus(),
                                child: Text(labels[key]!),
                              ),
                          ],
                        ),
                      ),
                    for (final key in labels.keys)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 16),
                        child: TextFormField(
                          controller: fields[key],
                          focusNode: focus[key],
                          enabled: form.active && !form.busy && !form.frozen,
                          decoration: InputDecoration(
                            labelText: labels[key],
                            errorMaxLines: 4,
                            helperText: key == 'audit_date'
                                ? 'YYYY-MM-DD'
                                : null,
                            counterText:
                                key == 'remarks' &&
                                    fields[key]!.text.runes.length >= 9000
                                ? '${fields[key]!.text.runes.length} / 10000'
                                : null,
                            suffixIcon: key == 'audit_date'
                                ? IconButton(
                                    tooltip: 'Choose audit date',
                                    onPressed:
                                        form.active &&
                                            !form.busy &&
                                            !form.frozen
                                        ? pickDate
                                        : null,
                                    icon: const Icon(Icons.calendar_today),
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
                              : (_) {
                                  final keys = labels.keys.toList();
                                  focus[keys[keys.indexOf(key) + 1]]!
                                      .requestFocus();
                                },
                          validator: (value) => form.active
                              ? form.validateField(key, value)
                              : null,
                          onChanged: (value) {
                            form.values[key] = value;
                            if (key == 'remarks') setState(() {});
                          },
                        ),
                      ),
                    if (form.message != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 16),
                        child: Semantics(
                          liveRegion: true,
                          child: Text(form.message!),
                        ),
                      ),
                    if (form.frozen && form.message == null)
                      const Text(
                        'This attempt is frozen. The server may already have saved it. Retry uses the same attempt.',
                      ),
                    Wrap(
                      spacing: 16,
                      runSpacing: 8,
                      children: [
                        FilledButton(
                          style: FilledButton.styleFrom(
                            minimumSize: const Size(88, 48),
                          ),
                          onPressed: form.canSave ? save : null,
                          child: Text(
                            form.busy
                                ? 'Saving…'
                                : form.frozen
                                ? 'Retry save'
                                : 'Save',
                          ),
                        ),
                        TextButton(
                          style: TextButton.styleFrom(
                            minimumSize: const Size(88, 48),
                          ),
                          onPressed: leave,
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
    ),
  );
  @override
  void dispose() {
    form.removeListener(changed);
    form.dispose();
    for (final field in fields.values) {
      field.dispose();
    }
    for (final node in focus.values) {
      node.dispose();
    }
    super.dispose();
  }
}
