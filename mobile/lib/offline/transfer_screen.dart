import 'dart:isolate';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../ui/core/content.dart';
import 'models.dart';
import 'transfer.dart';
import 'transfer_documents.dart';
import 'transfer_store.dart';

// A top-level seam prevents the isolate closure from capturing this screen's
// State, element tree or native handles.
Future<int> _recordCount(Uint8List bytes) =>
    Isolate.run(() => decodeTransfer(bytes).audits.length);

class OfflineTransferScreen extends StatefulWidget {
  const OfflineTransferScreen({
    super.key,
    required this.repository,
    this.importing = false,
    this.documents,
  });
  final OfflineTransferRepository repository;
  final bool importing;
  final TransferDocuments? documents;
  @override
  State<OfflineTransferScreen> createState() => _TransferState();
}

class _TransferState extends State<OfflineTransferScreen> {
  static bool _admitted = false;
  late final docs = widget.documents ?? TransferDocuments();
  final from = TextEditingController(), to = TextEditingController();
  final form = GlobalKey<FormState>();
  bool range = false,
      busy = false,
      canceled = false,
      ack = false,
      changed = false;
  String status = '', error = '';
  String? stage;
  Uint8List? input;
  ImportPreview? preview;
  int? prepared;
  bool get pending => busy;
  Future<void> work(Future<void> Function() action) async {
    if (busy) return;
    if (_admitted) {
      setState(
        () => error = 'Another transfer is running. Wait and try again.',
      );
      return;
    }
    _admitted = true;
    setState(() {
      busy = true;
      canceled = false;
      error = '';
    });
    try {
      await action();
    } catch (e) {
      if (mounted) {
        setState(
          () => error = e is PlatformException && e.code == 'cleanup_incomplete'
              ? 'Saving failed. An incomplete file may remain in the selected destination. Remove it before trying again.'
              : e is OfflineFailure
              ? e.message
              : e is FormatException
              ? 'This transfer is invalid or exceeds safe limits. Choose a valid file or narrow the date range.'
              : 'Transfer could not finish. Check records before retrying the same file.',
        );
      }
    } finally {
      _admitted = false;
      if (mounted) setState(() => busy = false);
    }
  }

  void phase(String value) {
    if (mounted) setState(() => status = value);
  }

  void checkCancel() {
    if (canceled) {
      throw const OfflineFailure(
        'canceled',
        'Transfer canceled before completion.',
      );
    }
  }

  Future<void> clean() async {
    final path = stage;
    stage = null;
    if (path != null) await docs.deleteStage(path);
  }

  Future<void> prepare() async {
    if (!form.currentState!.validate()) return;
    if (range && from.text.compareTo(to.text) > 0) {
      setState(
        () => error = 'The start date must be on or before the end date.',
      );
      return;
    }
    await work(() async {
      await clean();
      phase('Preparing');
      final bytes = await widget.repository.exportTransfer(
        dateFrom: range ? from.text : null,
        dateTo: range ? to.text : null,
        cancel: () => canceled,
      );
      checkCancel();
      final count = await _recordCount(bytes);
      stage = await docs.stage(bytes);
      checkCancel();
      if (mounted) {
        setState(() {
          prepared = count;
          status = 'Choose destination';
        });
      }
    });
  }

  Future<void> save() async => work(() async {
    if (stage == null) return;
    phase('Choose destination');
    final saved = await docs.saveStage(stage!, 'BHLI-audits.bhlitransfer');
    // A completed, verified provider copy remains successful even if cancel was late.
    if (saved) {
      phase('Transfer saved.');
      await cleanCompleted();
      if (mounted) setState(() => prepared = null);
    } else {
      phase(
        'Destination selection canceled. The prepared snapshot is ready to save.',
      );
    }
  });
  Future<void> choose() async => work(() async {
    await clean();
    input = null;
    preview = null;
    ack = false;
    phase('Reading');
    stage = await docs.pickImport();
    if (stage == null) {
      phase('File selection canceled.');
      return;
    }
    checkCancel();
    input = await docs.readStage(stage!);
    checkCancel();
    phase('Checking');
    final result = await widget.repository.previewTransfer(input!);
    checkCancel();
    if (mounted) {
      setState(() {
        preview = result;
        status = 'Preview';
      });
    }
  });
  Future<void> apply() async => work(() async {
    if (input == null ||
        preview == null ||
        (preview!.conflictIds.isNotEmpty && !ack)) {
      return;
    }
    phase(
      'Importing. Wait for the final result; finishing may already have committed.',
    );
    final result = await widget.repository.applyTransfer(
      input!,
      preview!,
      cancel: () => canceled,
    );
    // Do not reinterpret a committed import as canceled.
    changed = true;
    phase(
      'Imported ${result.imported}. Already here: ${result.duplicates}. Skipped different versions: ${result.conflicts}.',
    );
    if (mounted) {
      setState(() {
        preview = null;
        input = null;
      });
    }
    await cleanCompleted();
  });
  Future<void> cancel() async {
    canceled = true;
    try {
      await docs.cancel();
    } catch (_) {
      if (mounted) {
        setState(
          () => error = 'Cancel could not be delivered. Wait for the current result before retrying.',
        );
      }
      return;
    }
    if (mounted) {
      phase('Cancel requested. Waiting for the current operation to finish.');
    }
  }

  Future<void> cleanCompleted() async {
    try {
      await clean();
    } catch (_) {
      phase(
        '$status Private temporary cleanup failed. Restart the app before another transfer.',
      );
    }
  }

  Future<void> close() async {
    if (busy) return;
    try {
      await clean();
      if (!mounted) return;
      setState(() {});
      await WidgetsBinding.instance.endOfFrame;
      if (mounted) Navigator.pop(context, changed);
    } catch (_) {
      if (mounted) {
        setState(
          () => error = 'Private transfer cleanup failed. Close and reopen the app before retrying.',
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !pending && stage == null,
    onPopInvokedWithResult: (didPop, result) {
      if (!didPop && !pending) close();
    },
    child: Scaffold(
      appBar: AppBar(
        title: Text(widget.importing ? 'Import Audits' : 'Export Audits'),
        automaticallyImplyLeading: !pending,
      ),
      body: SafeArea(
        child: ContentWidth(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'Transfer includes complete available history and archived records. Protect files you share.',
                ),
                const SizedBox(height: 16),
                if (widget.importing) ...[
                  const Text(
                    'Only new audits will be added. Existing audits and their history stay unchanged. Later edits to audits already imported are not synchronized.',
                  ),
                  const SizedBox(height: 16),
                  OutlinedButton(
                    onPressed: busy ? null : choose,
                    child: const Text('Choose transfer file'),
                  ),
                  if (preview != null) ...[
                    Text('New: ${preview!.newIds.length}'),
                    Text('Already here: ${preview!.duplicateIds.length}'),
                    Text('Different version: ${preview!.conflictIds.length}'),
                    if (preview!.conflictIds.isNotEmpty)
                      CheckboxListTile(
                        contentPadding: EdgeInsets.zero,
                        value: ack,
                        onChanged: busy
                            ? null
                            : (v) => setState(() => ack = v ?? false),
                        title: const Text(
                          'I understand that different versions will be skipped.',
                        ),
                      ),
                    FilledButton(
                      onPressed:
                          busy || (preview!.conflictIds.isNotEmpty && !ack)
                          ? null
                          : apply,
                      child: const Text('Import new records only'),
                    ),
                  ],
                ] else ...[
                  Form(
                    key: form,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        CheckboxListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text(
                            'Use an inclusive audit-date range',
                          ),
                          value: range,
                          onChanged: busy
                              ? null
                              : (v) => setState(() => range = v ?? false),
                        ),
                        if (range) ...[
                          for (final entry in [
                            (from, 'Date from'),
                            (to, 'Date to'),
                          ])
                            Padding(
                              padding: const EdgeInsets.only(bottom: 16),
                              child: TextFormField(
                                controller: entry.$1,
                                enabled: !busy,
                                decoration: InputDecoration(
                                  labelText: entry.$2,
                                  helperText: 'YYYY-MM-DD',
                                  errorMaxLines: 3,
                                ),
                                validator: (v) =>
                                    v != null && validOfflineDate(v)
                                    ? null
                                    : 'Enter a valid date as YYYY-MM-DD.',
                              ),
                            ),
                        ],
                        const Text(
                          'All records are included when a date range is not selected.',
                        ),
                        FilledButton(
                          onPressed: busy ? null : prepare,
                          child: const Text('Prepare export'),
                        ),
                      ],
                    ),
                  ),
                  if (prepared != null) ...[
                    Text(
                      '$prepared audits prepared, including archived records.',
                    ),
                    const Text(
                      'The destination will contain this prepared snapshot. Later changes are outside this snapshot.',
                    ),
                    OutlinedButton(
                      onPressed: busy ? null : save,
                      child: const Text('Choose destination'),
                    ),
                  ],
                ],
                if (busy) const LinearProgressIndicator(),
                if (status.isNotEmpty)
                  Semantics(liveRegion: true, child: StatusMessage(status)),
                if (error.isNotEmpty)
                  Semantics(
                    liveRegion: true,
                    child: StatusMessage(error, error: true),
                  ),
                if (busy)
                  OutlinedButton(
                    onPressed: canceled ? null : cancel,
                    child: const Text('Cancel'),
                  ),
                if (!busy)
                  OutlinedButton(onPressed: close, child: const Text('Close')),
              ],
            ),
          ),
        ),
      ),
    ),
  );
  @override
  void dispose() {
    from.dispose();
    to.dispose();
    super.dispose();
  }
}
