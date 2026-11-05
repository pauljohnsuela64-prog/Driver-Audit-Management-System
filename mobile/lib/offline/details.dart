import 'package:flutter/material.dart';

import '../ui/core/content.dart';
import 'form.dart';
import 'models.dart';
import 'repository.dart';

class OfflineAuditDetails extends StatefulWidget {
  const OfflineAuditDetails({
    super.key,
    required this.repository,
    required this.id,
  });
  final OfflineRepository repository;
  final String id;
  @override
  State<OfflineAuditDetails> createState() => _OfflineAuditDetailsState();
}

class _OfflineAuditDetailsState extends State<OfflineAuditDetails> {
  LocalAudit? record;
  bool loading = true;
  bool busy = false;
  bool archiveConflict = false;
  bool leaving = false;
  String? error;
  String? success;
  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    if (!mounted) return;
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final result = await widget.repository.read(widget.id);
      if (mounted) {
        setState(() {
          record = result;
          archiveConflict = false;
        });
      }
    } catch (failure) {
      if (mounted) {
        setState(
          () => error = offlineError(failure, operation: 'refresh this audit'),
        );
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> edit() async {
    if (busy || loading) return;
    setState(() {
      busy = true;
      error = null;
    });
    LocalAudit? latest;
    LocalProfile? profile;
    try {
      latest = await widget.repository.read(widget.id);
      profile = await widget.repository.profile();
      if (mounted) setState(() => record = latest);
    } catch (failure) {
      if (mounted) {
        setState(
          () => error = offlineError(
            failure,
            operation: 'open this audit for editing',
          ),
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
    if (!mounted || latest == null || profile == null || latest.archived) {
      return;
    }
    final saved = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (_) => OfflineAuditForm(
          repository: widget.repository,
          profile: profile!,
          record: latest,
        ),
      ),
    );
    if (!mounted || saved != true) return;
    setState(() => success = 'Audit saved');
    await load();
  }

  Future<void> archive() async {
    if (busy || record == null || record!.archived || archiveConflict) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        scrollable: true,
        title: const Text('Archive this audit?'),
        content: const Text(
          'The audit and its history stay on this device. Archived audits cannot be edited.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Archive'),
          ),
        ],
      ),
    );
    if (!mounted || confirmed != true || busy) return;
    setState(() {
      busy = true;
      error = null;
    });
    var saved = false;
    try {
      await widget.repository.archive(widget.id, record!.revision);
      saved = true;
    } catch (failure) {
      if (mounted) {
        setState(() {
          archiveConflict =
              failure is OfflineFailure && failure.code == 'conflict';
          error = offlineError(failure, operation: 'confirm this archive');
        });
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
    if (!mounted) return;
    if (saved) {
      setState(() => leaving = true);
      Navigator.pop(context, true);
    }
  }

  void close() {
    if (busy || leaving) return;
    setState(() => leaving = true);
    Navigator.pop(context, success != null);
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: leaving,
    onPopInvokedWithResult: (didPop, result) {
      if (!didPop) close();
    },
    child: Scaffold(
      appBar: AppBar(
        title: const Text('Audit Details'),
        leading: IconButton(
          tooltip: 'Back',
          onPressed: busy ? null : close,
          icon: const Icon(Icons.arrow_back),
        ),
      ),
      body: SafeArea(
        child: ContentWidth(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (success != null) StatusMessage(success!),
                if (loading) const LinearProgressIndicator(),
                if (busy)
                  const StatusMessage(
                    'Working locally. Keep this screen open until the operation finishes.',
                  ),
                if (error != null) ...[
                  StatusMessage(error!, error: true),
                  OutlinedButton(
                    onPressed: busy || loading ? null : load,
                    child: Text(
                      archiveConflict ? 'Reload latest audit' : 'Retry',
                    ),
                  ),
                ],
                if (record != null) ...[
                  if (record!.archived) const StatusMessage('Archived'),
                  for (final entry in {
                    ...record!.values.toJson(),
                    'audited_by_name': record!.auditedByName,
                  }.entries)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            offlineFieldLabels[entry.key]!,
                            style: Theme.of(context).textTheme.labelLarge,
                          ),
                          const SizedBox(height: 4),
                          Text(entry.value as String? ?? '—'),
                        ],
                      ),
                    ),
                  const Text(
                    'Audited By is the original self-declared local profile name.',
                  ),
                  Text(
                    'Created: ${record!.createdAt.toUtc().toIso8601String()}',
                  ),
                  Text(
                    'Updated: ${record!.updatedAt.toUtc().toIso8601String()}',
                  ),
                  Text('Revision ${record!.revision}'),
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 16,
                    runSpacing: 8,
                    children: [
                      if (!record!.archived)
                        FilledButton(
                          onPressed: busy || loading ? null : edit,
                          child: const Text('Edit Audit'),
                        ),
                      OutlinedButton(
                        onPressed: busy
                            ? null
                            : () => Navigator.push(
                                context,
                                MaterialPageRoute<void>(
                                  builder: (_) => OfflineAuditHistory(
                                    repository: widget.repository,
                                    id: widget.id,
                                  ),
                                ),
                              ),
                        child: const Text('History'),
                      ),
                      if (!record!.archived)
                        TextButton(
                          onPressed: busy || loading || archiveConflict
                              ? null
                              : archive,
                          child: const Text('Archive Audit'),
                        ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    ),
  );
}

class OfflineAuditHistory extends StatefulWidget {
  const OfflineAuditHistory({
    super.key,
    required this.repository,
    required this.id,
  });
  final OfflineRepository repository;
  final String id;
  @override
  State<OfflineAuditHistory> createState() => _OfflineAuditHistoryState();
}

class _OfflineAuditHistoryState extends State<OfflineAuditHistory> {
  List<LocalEvent> events = [];
  int page = 1;
  bool loading = true;
  String? error;
  @override
  void initState() {
    super.initState();
    load(1);
  }

  Future<void> load(int target) async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final result = await widget.repository.history(
        widget.id,
        page: target,
        pageSize: 10,
      );
      if (mounted) {
        setState(() {
          events = result;
          page = target;
        });
      }
    } catch (failure) {
      if (mounted) {
        setState(
          () => error = offlineError(failure, operation: 'load history'),
        );
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('History')),
    body: SafeArea(
      child: ContentWidth(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Actors are self-declared local profiles. Times below are UTC.',
              ),
              if (loading) const LinearProgressIndicator(),
              if (error != null) ...[
                StatusMessage(error!, error: true),
                OutlinedButton(
                  onPressed: loading ? null : () => load(page),
                  child: const Text('Retry'),
                ),
              ],
              if (!loading && error == null && events.isEmpty)
                const StatusMessage('No more history'),
              for (final event in events)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          '${event.action} · Revision ${event.revision}',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        Text(event.actorName),
                        Text(event.createdAt.toUtc().toIso8601String()),
                        const SizedBox(height: 8),
                        for (final entry in offlineFieldLabels.entries)
                          if ((event.before?[entry.key] !=
                                  event.after?[entry.key]) ||
                              event.before == null)
                            Padding(
                              padding: const EdgeInsets.only(bottom: 12),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    entry.value,
                                    style: Theme.of(context)
                                        .textTheme
                                        .labelLarge,
                                  ),
                                  Text(
                                    'Before: ${event.before?[entry.key] ?? '—'}',
                                  ),
                                  Text(
                                    'After: ${event.after?[entry.key] ?? '—'}',
                                  ),
                                ],
                              ),
                            ),
                        if (event.action == 'ARCHIVE')
                          const Text(
                            'Active → Archived. Audit values and history preserved.',
                          ),
                      ],
                    ),
                  ),
                ),
              const SizedBox(height: 16),
              Text('History page $page'),
              Wrap(
                spacing: 16,
                runSpacing: 8,
                children: [
                  OutlinedButton(
                    onPressed: loading || page == 1
                        ? null
                        : () => load(page - 1),
                    child: const Text('Previous'),
                  ),
                  OutlinedButton(
                    onPressed: loading || events.length < 10
                        ? null
                        : () => load(page + 1),
                    child: const Text('Next'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    ),
  );
}
