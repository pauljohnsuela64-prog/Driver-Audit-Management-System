import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'models.dart';
import 'reporting.dart';

/// Only generated report stages cross this purpose-limited native seam.
class ReportDocuments {
  static const channel = MethodChannel('com.bhli.audit/reports_documents');
  Future<String> stage(Uint8List bytes) async {
    if (bytes.length > reportMaxBytes) {
      throw const OfflineFailure(
        'report_limit',
        'The report exceeds safe limits.',
      );
    }
    final path = await channel.invokeMethod<String>('createStage');
    if (path == null) {
      throw const FileSystemException('Private report staging unavailable.');
    }
    try {
      await File(path).writeAsBytes(bytes, flush: true);
      return path;
    } catch (_) {
      await deleteStage(path);
      rethrow;
    }
  }

  Future<bool> save(String path, {int remainingMillis = 600000}) async =>
      await channel.invokeMethod<bool>('saveStage', {
        'path': path,
        'remainingMillis': remainingMillis,
      }) ??
      false;
  Future<void> deleteStage(String path) =>
      channel.invokeMethod<void>('deleteStage', {'path': path});
  Future<void> cancel() => channel.invokeMethod<void>('cancel');
}

class OfflineReportScreen extends StatefulWidget {
  const OfflineReportScreen({
    super.key,
    required this.repository,
    required this.filter,
    this.documents,
  });
  final OfflineReportingRepository repository;
  final AuditFilter filter;
  final ReportDocuments? documents;
  @override
  State<OfflineReportScreen> createState() => _ReportState();
}

class _ReportState extends State<OfflineReportScreen> {
  static bool _admitted = false;
  late final documents = widget.documents ?? ReportDocuments();
  OfflineReportSnapshot? snapshot;
  bool loading = false, busy = false, cancelled = false;
  String? error, status;
  @override
  void initState() {
    super.initState();
    refresh();
  }

  Future<void> refresh() async {
    if (loading || busy) return;
    setState(() => loading = true);
    try {
      final value = await widget.repository.reportSnapshot(widget.filter);
      if (mounted) {
        setState(() {
          snapshot = value;
          error = null;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(
          () => error = e is OfflineFailure
              ? e.message
              : 'The report summary could not be loaded. Retry.',
        );
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> save() async {
    if (busy || loading) return;
    if (_admitted) {
      setState(() => error = 'Another report is running. Wait and try again.');
      return;
    }
    _admitted = true;
    setState(() {
      busy = true;
      cancelled = false;
      error = null;
      status = 'Preparing a new report snapshot...';
    });
    String? stage;
    var confirmedSave = false;
    final deadline = Stopwatch()..start();
    try {
      final full = await widget.repository.reportSnapshot(
        widget.filter,
        includeRows: true,
        cancel: () => cancelled || deadline.elapsed > reportMaxDuration,
      );
      if (mounted) {
        setState(() => snapshot = full);
      }
      final bytes = await encodeTextReport(full);
      if (cancelled) return;
      if (deadline.elapsed > reportMaxDuration) {
        throw const OfflineFailure(
          'report_limit',
          'Report preparation exceeded ten minutes. Narrow the applied filters.',
        );
      }
      stage = await documents.stage(bytes);
      if (cancelled) return;
      if (mounted) {
        setState(
          () => status =
              'Choose a new text file. Saving includes readback verification.',
        );
      }
      final remaining =
          reportMaxDuration.inMilliseconds - deadline.elapsedMilliseconds;
      if (remaining <= 0) {
        throw const OfflineFailure(
          'report_limit',
          'Report preparation exceeded ten minutes. Narrow the applied filters.',
        );
      }
      final saved = await documents.save(stage, remainingMillis: remaining);
      confirmedSave = saved;
      if (mounted) {
        setState(() {
          snapshot = full;
          status = saved
              ? 'Text report saved and verified. Protect this unencrypted file.'
              : 'No text report saved.';
        });
      }
    } catch (e) {
      if (mounted) {
        setState(
          () => error = e is OfflineFailure
              ? e.message
              : e is PlatformException && e.code == 'cleanup_incomplete'
              ? 'Saving failed. An incomplete newly created document may remain. Remove it from the selected destination.'
              : 'The report could not be saved. Check storage and retry.',
        );
      }
    } finally {
      if (stage != null) {
        try {
          await documents.deleteStage(stage);
        } catch (_) {
          if (mounted) {
            setState(
              () => error = [
                ?error,
                'Private report cleanup failed. An app-private temporary report may remain.',
              ].join('\n'),
            );
          }
        }
      }
      _admitted = false;
      if (mounted) {
        setState(() {
          busy = false;
          if (cancelled && !confirmedSave && error == null) {
            status = 'Report cancelled. No text report saved.';
          }
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = snapshot;
    return PopScope(
      canPop: !busy,
      child: Scaffold(
        appBar: AppBar(title: const Text('Report summary')),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text('Point-in-time local snapshot'),
            const Text(
              'Save text report takes a fresh snapshot of this applied query. Counts and snapshot time update after preparation.',
            ),
            const SizedBox(height: 12),
            Text(reportFilterDescription(widget.filter)),
            const SizedBox(height: 12),
            const Text(
              'Include archived changes the displayed result set. Active + archived equals the all-status matching total.',
            ),
            if (loading)
              const LinearProgressIndicator(
                semanticsLabel: 'Loading report summary',
              ),
            if (s != null) ...[
              Text('Snapshot UTC: ${s.snapshotUtc.toIso8601String()}'),
              Text('All-status matching total: ${s.total}'),
              Text('Active: ${s.active}'),
              Text('Archived: ${s.archived}'),
              Text('Displayed scope: ${s.displayed}'),
              const SizedBox(height: 12),
              const Text('Stations in displayed scope'),
              for (final station in s.stations)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Text(
                    '${station.other ? 'Other stations' : safeReportText(station.name)}: ${station.count}',
                  ),
                ),
              if (s.displayed == 0) const Text('Zero matching audits.'),
            ],
            if (error != null) Text(error!, semanticsLabel: error),
            if (status != null)
              Semantics(liveRegion: true, child: Text(status!)),
            if (busy)
              const LinearProgressIndicator(
                semanticsLabel: 'Preparing or saving report',
              ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: busy || loading || s == null ? null : save,
              child: const Text('Save text report'),
            ),
            OutlinedButton(
              onPressed: busy || loading ? null : refresh,
              child: const Text('Refresh with new snapshot'),
            ),
            TextButton(
              onPressed: busy ? null : () => Navigator.pop(context),
              child: const Text('Return to Driver Audits'),
            ),
            if (busy)
              OutlinedButton(
                onPressed: () async {
                  setState(() => cancelled = true);
                  await documents.cancel();
                },
                child: const Text('Cancel report'),
              ),
            const Text(
              'Offline development edition. The saved UTF-8 text report is unencrypted. After saving, share it through Android Files if needed.',
            ),
          ],
        ),
      ),
    );
  }
}
