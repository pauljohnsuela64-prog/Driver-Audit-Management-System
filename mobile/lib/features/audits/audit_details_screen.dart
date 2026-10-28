import 'package:flutter/material.dart';

import '../../core/network/api_failure.dart';
import '../../ui/core/content.dart';
import '../auth/session_controller.dart';
import 'models.dart';

class AuditDetailsScreen extends StatefulWidget {
  const AuditDetailsScreen({
    super.key,
    required this.session,
    required this.auditId,
  });
  final SessionController session;
  final int auditId;
  @override
  State<AuditDetailsScreen> createState() => _AuditDetailsScreenState();
}

class _AuditDetailsScreenState extends State<AuditDetailsScreen> {
  AuditRecord? _record;
  String? _error;
  bool _loading = false;
  int _request = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final request = ++_request;
    final generation = widget.session.generation;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final record = await widget.session.fetchAudit(widget.auditId);
      if (!mounted ||
          request != _request ||
          generation != widget.session.generation) {
        return;
      }
      setState(() {
        _record = record;
      });
    } on ApiFailure catch (failure) {
      if (!mounted ||
          request != _request ||
          generation != widget.session.generation) {
        return;
      }
      setState(() {
        _error = failure.message;
        if (failure.status == 404) _record = null;
      });
    } catch (_) {
      if (!mounted ||
          request != _request ||
          generation != widget.session.generation) {
        return;
      }
      setState(() {
        _error = 'Unable to load this audit. Try again.';
      });
    } finally {
      if (mounted &&
          request == _request &&
          generation == widget.session.generation) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  Widget _field(String label, String? value) => Padding(
    padding: const EdgeInsets.only(bottom: 24),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Theme.of(context).textTheme.labelLarge),
        const SizedBox(height: 8),
        SelectableText(
          value ?? '—',
          style: Theme.of(context).textTheme.bodyLarge,
        ),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) {
    final record = _record;
    return Scaffold(
      appBar: AppBar(title: const Text('Audit details')),
      body: SafeArea(
        child: ContentWidth(
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              Text(
                'Record #${widget.auditId}',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 16),
              Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton.icon(
                  onPressed: _loading ? null : _load,
                  icon: const Icon(Icons.refresh_outlined),
                  label: const Text('Refresh'),
                ),
              ),
              if (_loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16),
                  child: LinearProgressIndicator(
                    semanticsLabel: 'Loading audit details',
                  ),
                ),
              if (_error case final message?) ...[
                if (record != null)
                  const StatusMessage(
                    'Not refreshed. This audit may be out of date.',
                    error: true,
                  ),
                StatusMessage(message, error: true),
                OutlinedButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('Back to audits'),
                ),
              ],
              if (record != null) ...[
                const SizedBox(height: 16),
                _field('Driver Name', record.driverName),
                _field('Helper Name', record.helperName),
                _field('Audit Date', record.auditDate),
                _field('Station', record.station),
                _field('Plate Number', record.plateNumber),
                _field('Remarks', record.remarks),
                _field('Audited By', record.auditedByName),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
