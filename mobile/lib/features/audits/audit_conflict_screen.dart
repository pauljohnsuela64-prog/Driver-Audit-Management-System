import 'package:flutter/material.dart';

import 'audit_form_controller.dart';

/// Same-route comparison: the form continues to own its session-only draft.
class AuditConflictScreen extends StatelessWidget {
  const AuditConflictScreen({
    super.key,
    required this.form,
    required this.onSave,
    required this.onDiscard,
    required this.onRetry,
  });
  final AuditFormController form;
  final VoidCallback onSave, onDiscard, onRetry;
  static const labels = {
    'driver_name': 'Driver Name',
    'helper_name': 'Helper Name',
    'audit_date': 'Audit Date',
    'station': 'Station',
    'plate_number': 'Plate Number',
    'remarks': 'Remarks',
  };
  String value(Object? value) => value == null ? 'Not provided' : '$value';
  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    padding: const EdgeInsets.all(16),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'This audit changed. Review the latest version before saving.',
        ),
        const SizedBox(height: 16),
        const Text(
          'Unchanged fields use the latest saved values. Choose which value to keep for every differing proposed field.',
        ),
        if (form.busy)
          const LinearProgressIndicator(semanticsLabel: 'Reviewing audit'),
        if (form.reviewedRecord != null)
          for (final key in labels.keys.where(
            (key) =>
                !form.reviewFields.contains(key) &&
                form.originalValues[key] != form.latestValues[key],
          ))
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      labels[key]!,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const Text(
                      'Changed by another operation. Latest value is preserved.',
                    ),
                    const Text('Latest saved value'),
                    SelectableText(value(form.latestValues[key])),
                  ],
                ),
              ),
            ),
        if (form.reviewedRecord != null)
          for (final key in form.reviewFields)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      labels[key]!,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    if (form.originalValues[key] != form.latestValues[key])
                      const Text(
                        'Changed by another operation since editing began.',
                      ),
                    const SizedBox(height: 8),
                    const Text('Your proposed value'),
                    SelectableText(value(form.proposedValues[key])),
                    const SizedBox(height: 16),
                    const Text('Latest saved value'),
                    SelectableText(value(form.latestValues[key])),
                    if (form.proposedValues[key] != form.latestValues[key]) ...[
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          ChoiceChip(
                            materialTapTargetSize: MaterialTapTargetSize.padded,
                            label: const Text('Use my proposed value'),
                            selected: form.reviewChoices[key] == true,
                            onSelected: form.busy
                                ? null
                                : (_) => form.chooseReview(key, true),
                          ),
                          ChoiceChip(
                            materialTapTargetSize: MaterialTapTargetSize.padded,
                            label: const Text('Use latest saved value'),
                            selected: form.reviewChoices[key] == false,
                            onSelected: form.busy
                                ? null
                                : (_) => form.chooseReview(key, false),
                          ),
                        ],
                      ),
                    ] else
                      const Text('Your proposed value is already saved.'),
                  ],
                ),
              ),
            ),
        if (form.message != null)
          Semantics(liveRegion: true, child: Text(form.message!)),
        const SizedBox(height: 16),
        Wrap(
          spacing: 16,
          runSpacing: 8,
          children: [
            FilledButton(
              onPressed: form.canSaveReviewed ? onSave : null,
              child: const Text('Save reviewed changes'),
            ),
            if (form.reviewedRecord == null)
              OutlinedButton(
                onPressed: form.busy ? null : onRetry,
                child: const Text('Retry latest audit'),
              ),
            TextButton(
              onPressed: form.busy ? null : onDiscard,
              child: const Text('Discard my changes'),
            ),
          ],
        ),
      ],
    ),
  );
}
