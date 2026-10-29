import 'package:flutter/material.dart';

import '../../core/network/api_failure.dart';
import '../../ui/core/content.dart';
import '../auth/session_controller.dart';
import 'models.dart';
import 'audit_history_screen.dart';
import 'audit_form_screen.dart';
import 'audit_permissions.dart';
import 'audit_mutation_controller.dart';

class AuditDetailsScreen extends StatefulWidget {
  const AuditDetailsScreen({
    super.key,
    required this.session,
    required this.auditId,
    this.initialRecord,
    this.includeArchived = false,
    this.savedMessage,
    this.onSaved,
    this.onVisibilityChanged,
    this.onArchived,
  });
  final SessionController session;
  final int auditId;
  final bool includeArchived;
  final AuditRecord? initialRecord;
  final String? savedMessage;
  final Future<void> Function(AuditFormResult)? onSaved;
  final Future<void> Function()? onVisibilityChanged;
  final Future<void> Function()? onArchived;
  @override
  State<AuditDetailsScreen> createState() => _AuditDetailsScreenState();
}

class _AuditDetailsScreenState extends State<AuditDetailsScreen> {
  AuditRecord? _record;
  String? _error;
  bool _loading = false;
  int _request = 0;
  bool _editing = false;
  String? _savedMessage;
  bool _archiveDialog = false;

  @override
  void initState() {
    super.initState();
    _record = widget.initialRecord;
    _savedMessage = widget.savedMessage;
    _generation = widget.session.generation;
    widget.session.addListener(_sessionChanged);
    _load();
  }

  void _sessionChanged() {
    final user = widget.session.user;
    final changedSession =
        user == null || widget.session.generation != _generation;
    if (_archiveDialog && mounted && (changedSession || user.role != 'ADMIN')) {
      Navigator.of(context, rootNavigator: true).pop(false);
      _archiveDialog = false;
    }
    if (mounted) {
      setState(() {
        if (changedSession) {
          _record = null;
          _error = null;
          _savedMessage = null;
        } else if (_record?.deletedAt != null &&
            !AuditPermissions.canIncludeArchived(user)) {
          _record = null;
          _savedMessage = null;
        }
      });
    }
  }

  late final int _generation;

  bool get _archiveNeedsReview {
    final state = widget.session.mutations.state;
    return state.auditId == widget.auditId &&
        state.kind == AuditMutationKind.delete &&
        {
          AuditMutationPhase.unknown,
          AuditMutationPhase.conflict,
        }.contains(state.phase);
  }

  Future<void> _archive() async {
    final user = widget.session.user;
    if (_editing || _loading || user?.role != 'ADMIN') return;
    final generation = widget.session.generation;
    setState(() {
      _editing = true;
      _error = null;
    });
    try {
      final needsReview = _archiveNeedsReview;
      final fresh = needsReview
          ? await widget.session.reviewMutation()
          : await widget.session.fetchAudit(widget.auditId);
      if (!mounted || generation != widget.session.generation) return;
      if (widget.session.user?.role != 'ADMIN') {
        throw ApiFailure.fromStatus(403);
      }
      setState(() => _record = fresh);
      if (fresh.deletedAt != null) {
        setState(
          () => _savedMessage = 'This audit is archived. The earlier archive response was not confirmed.',
        );
        widget.session.mutations.acknowledgeReview();
        await widget.onVisibilityChanged?.call();
        return;
      }
      if (!AuditPermissions.canDelete(widget.session.user!, fresh) ||
          fresh.etag == null) {
        throw ApiFailure.fromStatus(403);
      }
      _archiveDialog = true;
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          scrollable: true,
          title: const Text('Archive this audit?'),
          content: Text(
            'Record #${fresh.id}\nDriver Name: ${fresh.driverName}\nPlate Number: ${fresh.plateNumber}\n\nIt will leave the active list. Its history is retained.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Archive audit'),
            ),
          ],
        ),
      );
      _archiveDialog = false;
      if (!mounted ||
          generation != widget.session.generation ||
          confirmed != true) {
        return;
      }
      if (widget.session.user?.role != 'ADMIN') {
        throw ApiFailure.fromStatus(403);
      }
      if (needsReview) {
        if (!identical(widget.session.mutations.state.latest, fresh)) {
          throw ApiFailure.busy;
        }
        widget.session.mutations.acknowledgeReview();
      }
      await widget.session.deleteAudit(fresh.id, fresh.etag!);
      if (!mounted || generation != widget.session.generation) return;
      setState(() {
        _record = null;
        _savedMessage = 'Audit archived.';
      });
      try {
        await (widget.onArchived ?? widget.onVisibilityChanged)?.call();
      } catch (_) {
        if (mounted && generation == widget.session.generation) {
          setState(
            () => _savedMessage =
                'Audit archived. The list could not be refreshed.',
          );
        }
      }
    } on AuditMutationFailure catch (error) {
      if (!mounted || generation != widget.session.generation) return;
      setState(() {
        _error = error.failure.status == 412 || error.failure.status == 409
            ? 'This audit changed. Review it again and confirm before archiving.'
            : error.unconfirmed
            ? 'Archive not confirmed. The server may already have archived this audit. Review its current state before another action.'
            : error.failure.message;
        if (error.failure.status == 403 || error.failure.status == 404) {
          _record = null;
        }
      });
      if (error.failure.status == 403) await widget.session.verifyOnResume();
    } on ApiFailure catch (error) {
      if (!mounted || generation != widget.session.generation) return;
      setState(() {
        _error = error.status == 404
            ? 'This audit is unavailable. Its archive outcome is not confirmed.'
            : error.message;
        if (error.status == 403 || error.status == 404) _record = null;
      });
      if (error.status == 403) await widget.session.verifyOnResume();
    } catch (_) {
      if (mounted && generation == widget.session.generation) {
        setState(
          () =>
              _error = 'Unable to review this audit. No archive is confirmed.',
        );
      }
    } finally {
      if (mounted && generation == widget.session.generation) {
        setState(() => _editing = false);
      }
    }
  }

  Future<void> _edit() async {
    final original = _record;
    final user = widget.session.user;
    if (_loading ||
        _editing ||
        original == null ||
        user == null ||
        !AuditPermissions.canEdit(user, original)) {
      return;
    }
    final generation = widget.session.generation;
    setState(() {
      _editing = true;
      _error = null;
    });
    try {
      final mutation = widget.session.mutations.state;
      final needsReview = {
        AuditMutationPhase.unknown,
        AuditMutationPhase.conflict,
      }.contains(mutation.phase);
      if (needsReview &&
          (mutation.auditId != widget.auditId ||
              widget.session.mutations.pendingCreate != null)) {
        throw ApiFailure.busy;
      }
      final fresh = needsReview
          ? await widget.session.reviewMutation()
          : await widget.session.fetchAudit(widget.auditId);
      if (!mounted || generation != widget.session.generation) return;
      final current = widget.session.user;
      if (current == null || !AuditPermissions.canEdit(current, fresh)) {
        throw ApiFailure.fromStatus(403);
      }
      if (fresh.etag == null) throw ApiFailure.protocol;
      if (needsReview) {
        final useLatest = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            scrollable: true,
            title: const Text('Previous save needs review'),
            content: const Text(
              'The previous save may have completed or conflicted. Latest values have been reloaded. Discard the previous draft and edit these latest values? Nothing will be submitted automatically.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Cancel'),
              ),
              TextButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Use latest values'),
              ),
            ],
          ),
        );
        if (!mounted ||
            generation != widget.session.generation ||
            useLatest != true) {
          return;
        }
        if (!identical(widget.session.mutations.state.latest, fresh)) {
          throw ApiFailure.busy;
        }
        widget.session.mutations.acknowledgeReview();
      }
      setState(() => _record = fresh);
      final result = await Navigator.of(context).push<AuditFormResult>(
        MaterialPageRoute(
          builder: (_) =>
              AuditFormScreen(session: widget.session, record: fresh),
        ),
      );
      if (!mounted || generation != widget.session.generation) return;
      if (result == null) {
        final outcome = widget.session.mutations.state;
        if (outcome.auditId == widget.auditId &&
            (outcome.failure?.status == 403 ||
                outcome.failure?.status == 404)) {
          setState(() => _record = null);
        }
        await widget.onVisibilityChanged?.call();
        if (mounted && generation == widget.session.generation) await _load();
        return;
      }
      setState(() {
        _record = result.record;
        _savedMessage = 'Audit saved.';
      });
      // Refresh failures are separate from the already confirmed mutation.
      try {
        await widget.onSaved?.call(result);
      } catch (_) {
        if (mounted && generation == widget.session.generation) {
          setState(
            () =>
                _savedMessage = 'Audit saved. The list could not be refreshed.',
          );
        }
      }
      if (mounted && generation == widget.session.generation) await _load();
    } on ApiFailure catch (failure) {
      if (mounted && generation == widget.session.generation) {
        setState(() {
          _error = failure.message;
          if (failure.status == 403 || failure.status == 404) _record = null;
        });
      }
    } catch (_) {
      if (mounted && generation == widget.session.generation) {
        setState(
          () => _error =
              'Unable to open editing. Reload the audit and try again.',
        );
      }
    } finally {
      if (mounted && generation == widget.session.generation) {
        setState(() => _editing = false);
      }
    }
  }

  Future<void> _load() async {
    final request = ++_request;
    final generation = widget.session.generation;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final record = await widget.session.fetchAudit(
        widget.auditId,
        includeDeleted: widget.includeArchived,
      );
      if (!mounted ||
          request != _request ||
          generation != widget.session.generation) {
        return;
      }
      setState(() {
        if (widget.includeArchived && widget.session.user?.role != 'ADMIN') {
          return;
        }
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
        if (failure.status == 404 || failure.status == 403) _record = null;
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
              if (_savedMessage case final message?) StatusMessage(message),
              if (record?.deletedAt != null)
                const ListTile(
                  leading: Icon(Icons.archive_outlined),
                  title: Text('Archived \u00b7 Read-only'),
                  contentPadding: EdgeInsets.zero,
                ),
              if (widget.session.user?.role == 'ADMIN' &&
                  (_archiveNeedsReview ||
                      (record != null &&
                          AuditPermissions.canDelete(
                            widget.session.user!,
                            record,
                          ))))
                Align(
                  alignment: Alignment.centerLeft,
                  child: OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Theme.of(context).colorScheme.error,
                    ),
                    onPressed: _loading || _editing ? null : _archive,
                    icon: const Icon(Icons.archive_outlined),
                    label: Text(
                      _archiveNeedsReview
                          ? 'Review archive outcome'
                          : 'Archive audit',
                    ),
                  ),
                ),
              if (record != null &&
                  widget.session.user != null &&
                  AuditPermissions.canEdit(widget.session.user!, record))
                Align(
                  alignment: Alignment.centerLeft,
                  child: FilledButton.icon(
                    onPressed: _loading || _editing || _archiveNeedsReview
                        ? null
                        : _edit,
                    icon: const Icon(Icons.edit_outlined),
                    label: const Text('Edit'),
                  ),
                ),
              if (record != null &&
                  widget.session.user != null &&
                  (record.deletedAt == null ||
                      (widget.includeArchived &&
                          AuditPermissions.canIncludeArchived(
                            widget.session.user!,
                          ))))
                Align(
                  alignment: Alignment.centerLeft,
                  child: OutlinedButton.icon(
                    onPressed: _loading || _editing
                        ? null
                        : () => Navigator.of(context).push<void>(
                            MaterialPageRoute(
                              builder: (_) => AuditHistoryScreen(
                                session: widget.session,
                                auditId: widget.auditId,
                                includeArchived: widget.includeArchived,
                              ),
                            ),
                          ),
                    icon: const Icon(Icons.history),
                    label: const Text('History'),
                  ),
                ),
              Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton.icon(
                  onPressed: _loading || _editing ? null : _load,
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

  @override
  void dispose() {
    widget.session.removeListener(_sessionChanged);
    super.dispose();
  }
}
