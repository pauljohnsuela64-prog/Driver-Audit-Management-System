import 'package:flutter/material.dart';

import '../../ui/core/content.dart';
import '../auth/session_controller.dart';
import 'audit_history_controller.dart';
import 'audit_history_models.dart';

class AuditHistoryScreen extends StatefulWidget {
  const AuditHistoryScreen({
    super.key,
    required this.session,
    required this.auditId,
    this.includeArchived = false,
  });
  final SessionController session;
  final int auditId;
  final bool includeArchived;
  @override
  State<AuditHistoryScreen> createState() => _AuditHistoryScreenState();
}

class _AuditHistoryScreenState extends State<AuditHistoryScreen> {
  late final AuditHistoryController _history;
  @override
  void initState() {
    super.initState();
    _history = AuditHistoryController(
      widget.session,
      widget.auditId,
      includeArchived: widget.includeArchived,
    )..addListener(_changed);
    _history.refresh();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _history.removeListener(_changed);
    _history.dispose();
    super.dispose();
  }

  static const _labels = {
    'driver_name': 'Driver Name',
    'helper_name': 'Helper Name',
    'audit_date': 'Audit Date',
    'station': 'Station',
    'plate_number': 'Plate Number',
    'remarks': 'Remarks',
    'audited_by_name': 'Audited By',
  };
  Widget _comparison(
    String label,
    String? before,
    String? after, {
    required bool created,
  }) => Padding(
    padding: const EdgeInsets.only(top: 16),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Theme.of(context).textTheme.titleSmall),
        if (!created) ...[
          const SizedBox(height: 8),
          const Text('Previous value'),
          SelectableText(before ?? 'Not provided'),
        ],
        const SizedBox(height: 8),
        const Text('Updated value'),
        SelectableText(after ?? 'Not provided'),
      ],
    ),
  );
  String _localTime(DateTime instant) {
    final local = instant.toLocal();
    final offset = local.timeZoneOffset;
    final sign = offset.isNegative ? '-' : '+';
    final minutes = offset.inMinutes.abs();
    return '${local.toIso8601String()} ${local.timeZoneName} (UTC$sign${(minutes ~/ 60).toString().padLeft(2, '0')}:${(minutes % 60).toString().padLeft(2, '0')})';
  }

  Widget _event(AuditHistoryEvent event) {
    final created = event.action == 'CREATE';
    final fields = _labels.keys.where(
      (key) => created || event.before!.fields[key] != event.after.fields[key],
    );
    final action = switch (event.action) {
      'CREATE' => 'Created',
      'UPDATE' => 'Updated',
      _ => 'Archived',
    };
    final actor = event.actorUserId == widget.session.user?.id
        ? 'Changed by you · User #${event.actorUserId}'
        : 'Changed by User #${event.actorUserId}';
    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(action, style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 8),
                Text(actor),
                const SizedBox(height: 8),
                Text(_localTime(event.createdAt)),
              ],
            ),
          ),
          ExpansionTile(
            key: ValueKey('history-${event.id}'),
            title: const Text('View changes and UTC time'),
            expandedCrossAxisAlignment: CrossAxisAlignment.start,
            childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            children: [
              SelectableText(
                'UTC: ${event.createdAt.toUtc().toIso8601String()}',
              ),
              for (final key in fields)
                _comparison(
                  _labels[key]!,
                  event.before?.fields[key],
                  event.after.fields[key],
                  created: created,
                ),
              if (event.action == 'DELETE')
                _comparison('Status', 'Active', 'Archived', created: false),
              if (!created && fields.isEmpty && event.action != 'DELETE')
                const Padding(
                  padding: EdgeInsets.only(top: 16),
                  child: Text('No business field values changed.'),
                ),
            ],
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final page = _history.page;
    return Scaffold(
      appBar: AppBar(title: const Text('Audit history')),
      body: SafeArea(
        child: ContentWidth(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                'Record #${widget.auditId}',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 16),
              const Text('Oldest first · 10 events per page'),
              const SizedBox(height: 8),
              const Text(
                'Account IDs identify action authors. Audited By is the original audit attribution.',
              ),
              const SizedBox(height: 16),
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: [
                  OutlinedButton.icon(
                    onPressed: _history.loading || _history.unavailable
                        ? null
                        : _history.refresh,
                    icon: const Icon(Icons.refresh_outlined),
                    label: const Text('Refresh'),
                  ),
                ],
              ),
              if (_history.loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16),
                  child: LinearProgressIndicator(
                    semanticsLabel: 'Loading audit history',
                  ),
                ),
              if (_history.unavailable)
                const StatusMessage(
                  'This audit history is unavailable.',
                  error: true,
                ),
              if (_history.error case final error?) ...[
                StatusMessage(error, error: true),
                if (!_history.unavailable)
                  Align(
                    alignment: Alignment.centerLeft,
                    child: OutlinedButton(
                      onPressed: _history.loading ? null : _history.retry,
                      child: const Text('Retry'),
                    ),
                  ),
              ],
              if (page != null) ...[
                if (page.items.isEmpty)
                  const StatusMessage('No history events available.'),
                const SizedBox(height: 16),
                for (final event in page.items) _event(event),
                Wrap(
                  alignment: WrapAlignment.center,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  spacing: 16,
                  runSpacing: 12,
                  children: [
                    OutlinedButton(
                      onPressed: _history.loading || _history.pageNumber <= 1
                          ? null
                          : _history.previous,
                      child: const Text('Previous'),
                    ),
                    Text(
                      'Page ${_history.pageNumber} of ${page.totalPages} · ${page.total} events',
                    ),
                    OutlinedButton(
                      onPressed:
                          _history.loading ||
                              _history.pageNumber >= page.totalPages ||
                              _history.pageNumber >= 10000
                          ? null
                          : _history.next,
                      child: const Text('Next'),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
