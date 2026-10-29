import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/network/api_failure.dart';
import '../../ui/core/content.dart';
import '../auth/session_controller.dart';
import 'audit_list_controller.dart';
import 'audit_details_screen.dart';
import 'models.dart';
import 'audit_form_screen.dart';
import 'audit_mutation_controller.dart';
import 'audit_permissions.dart';
import 'audit_draft.dart';

class AuditListScreen extends StatefulWidget {
  const AuditListScreen({
    super.key,
    required this.session,
    required this.onSettings,
  });
  final SessionController session;
  final VoidCallback onSettings;
  @override
  State<AuditListScreen> createState() => _AuditListScreenState();
}

class _AuditListScreenState extends State<AuditListScreen> {
  late final AuditListController _list;
  final _search = TextEditingController();
  final _scroll = ScrollController();
  String _searchField = 'Driver name';
  String _sort = '-id';
  DateTime? _from;
  DateTime? _to;
  String? _validation;
  String? _savedMessage;
  String? _savedKey;
  bool _openingForm = false;
  bool get _needsReload =>
      widget.session.mutations.pendingCreate == null &&
      {
        AuditMutationPhase.unknown,
        AuditMutationPhase.conflict,
      }.contains(widget.session.mutations.state.phase);

  @override
  void initState() {
    super.initState();
    _list = AuditListController(widget.session)..addListener(_changed);
    widget.session.mutations.addListener(_mutationChanged);
    _list.refresh();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  void _mutationChanged() {
    if (!mounted) return;
    final state = widget.session.mutations.state;
    if (state.phase == AuditMutationPhase.sending) _savedMessage = null;
    if (state.phase == AuditMutationPhase.confirmed && state.record != null) {
      unawaited(
        _afterSaved(AuditFormResult(state.record!, replayed: state.replayed)),
      );
    }
    _changed();
  }

  String _saveMessage(AuditFormResult result) {
    final saved = result.replayed
        ? 'Previously saved audit recovered.'
        : 'Audit saved.';
    return _filtered
        ? '$saved Active filters are preserved; this audit may not appear in the list.'
        : saved;
  }

  Future<void> _afterSaved(AuditFormResult result) async {
    if (!mounted || widget.session.user == null) return;
    final key =
        '${widget.session.generation}:${result.record.id}:${result.record.version}';
    if (_savedKey == key) return;
    _savedKey = key;
    setState(() => _savedMessage = _saveMessage(result));
    await _list.refresh();
  }

  Future<void> _newAudit({bool review = false}) async {
    if (_openingForm || !mounted) return;
    setState(() {
      _openingForm = true;
      _savedMessage = null;
      _validation = null;
    });
    try {
      await _openNewAudit(review: review);
    } finally {
      if (mounted) setState(() => _openingForm = false);
    }
  }

  Future<void> _openNewAudit({bool review = false}) async {
    final user = widget.session.user;
    if (user == null ||
        !AuditPermissions.canCreate(user) ||
        widget.session.mutations.busy) {
      return;
    }
    if (_needsReload) {
      setState(
        () => _validation = 'A previous audit save needs review. Open that audit and reload it before another save.',
      );
      return;
    }
    final generation = widget.session.generation;
    PendingAuditCreate? pending = widget.session.mutations.pendingCreate;
    if (pending != null && !review) {
      final choice = await showDialog<String>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Unconfirmed audit save'),
          content: const SingleChildScrollView(
            child: Text(
              'This audit may already exist. Resume the same save, or abandon its retry information. Creating again after abandonment could duplicate an audit.',
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(context, 'resume'),
              child: const Text('Resume unconfirmed save'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(context, 'abandon'),
              child: const Text('Abandon retry information'),
            ),
          ],
        ),
      );
      if (!mounted ||
          generation != widget.session.generation ||
          choice == null) {
        return;
      }
      if (choice == 'abandon') {
        widget.session.mutations.abandonCreate(acknowledgeDuplicateRisk: true);
        pending = null;
      }
    }
    if (!mounted || generation != widget.session.generation) return;
    final result = await Navigator.of(context).push<AuditFormResult>(
      MaterialPageRoute(
        builder: (_) =>
            AuditFormScreen(session: widget.session, pendingCreate: pending),
      ),
    );
    if (!mounted || generation != widget.session.generation || result == null) {
      return;
    }
    await _afterSaved(result);
    if (!mounted || generation != widget.session.generation) return;
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => AuditDetailsScreen(
          session: widget.session,
          auditId: result.record.id,
          initialRecord: result.record,
          savedMessage: _saveMessage(result),
          onSaved: _afterSaved,
          onVisibilityChanged: _list.refresh,
        ),
      ),
    );
  }

  @override
  void dispose() {
    widget.session.mutations.removeListener(_mutationChanged);
    _list.removeListener(_changed);
    _list.dispose();
    _search.dispose();
    _scroll.dispose();
    super.dispose();
  }

  String _date(DateTime date) =>
      '${date.year.toString().padLeft(4, '0')}-'
      '${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';

  void _apply() {
    try {
      final query = AuditQuery(
        driverName: _searchField == 'Driver name' ? _search.text : null,
        plateNumber: _searchField == 'Plate number' ? _search.text : null,
        station: _searchField == 'Station' ? _search.text : null,
        dateFrom: _from == null ? null : _date(_from!),
        dateTo: _to == null ? null : _date(_to!),
        sort: _sort,
      );
      setState(() {
        _validation = null;
        _savedMessage = null;
      });
      FocusScope.of(context).unfocus();
      _list.apply(query);
    } on ApiFailure catch (_) {
      setState(() {
        _validation = _from != null && _to != null && _from!.isAfter(_to!)
            ? 'From date must be on or before To date.'
            : 'Search must be no more than 200 characters.';
      });
    }
  }

  void _clear() {
    setState(() {
      _search.clear();
      _from = null;
      _to = null;
      _sort = '-id';
      _validation = null;
      _savedMessage = null;
    });
    _list.apply(AuditQuery());
  }

  Future<void> _pickDate(bool from) async {
    final selected = await showDatePicker(
      context: context,
      initialDate: (from ? _from : _to) ?? DateTime.now(),
      firstDate: DateTime(1000),
      lastDate: DateTime(9999, 12, 31),
      helpText: from ? 'Inclusive From date' : 'Inclusive To date',
    );
    if (!mounted || selected == null) return;
    setState(() {
      if (from) {
        _from = selected;
      } else {
        _to = selected;
      }
    });
  }

  bool get _filtered {
    final query = _list.query;
    return query.driverName != null ||
        query.plateNumber != null ||
        query.station != null ||
        query.dateFrom != null ||
        query.dateTo != null;
  }

  Widget _filters() => Padding(
    padding: const EdgeInsets.all(16),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Driver Audits', style: Theme.of(context).textTheme.headlineSmall),
        if (widget.session.user case final user?)
          if (AuditPermissions.canCreate(user))
            Align(
              alignment: Alignment.centerLeft,
              child: Padding(
                padding: const EdgeInsets.only(top: 12),
                child: FilledButton.icon(
                  onPressed: widget.session.mutations.busy || _openingForm
                      ? null
                      : () => _newAudit(),
                  icon: const Icon(Icons.add),
                  label: const Text('New Audit'),
                ),
              ),
            ),
        if (widget.session.mutations.pendingCreate != null) ...[
          StatusMessage(
            widget.session.mutations.busy
                ? 'Audit save in progress.'
                : 'Unconfirmed audit save. The audit may already exist.',
            error: true,
          ),
          Align(
            alignment: Alignment.centerLeft,
            child: OutlinedButton(
              onPressed: widget.session.mutations.busy || _openingForm
                  ? null
                  : () => _newAudit(review: true),
              child: const Text('Review unconfirmed save'),
            ),
          ),
        ],
        if (_needsReload && widget.session.mutations.state.auditId != null) ...[
          const StatusMessage(
            'A previous audit save needs reload. It may already have completed.',
            error: true,
          ),
          Align(
            alignment: Alignment.centerLeft,
            child: OutlinedButton(
              onPressed: () => Navigator.of(context).push<void>(
                MaterialPageRoute(
                  builder: (_) => AuditDetailsScreen(
                    session: widget.session,
                    auditId: widget.session.mutations.state.auditId!,
                    onSaved: _afterSaved,
                    onVisibilityChanged: _list.refresh,
                  ),
                ),
              ),
              child: const Text('Open audit to reload'),
            ),
          ),
        ],
        if (_savedMessage case final message?) StatusMessage(message),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          initialValue: _searchField,
          decoration: const InputDecoration(labelText: 'Search by'),
          isExpanded: true,
          items: ['Driver name', 'Plate number', 'Station']
              .map(
                (field) => DropdownMenuItem(value: field, child: Text(field)),
              )
              .toList(),
          onChanged: (field) {
            if (field != null) {
              setState(() {
                _searchField = field;
              });
            }
          },
        ),
        const SizedBox(height: 12),
        TextFormField(
          controller: _search,
          decoration: const InputDecoration(labelText: 'Search audits'),
          textInputAction: TextInputAction.search,
          onFieldSubmitted: (_) => _apply(),
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            FilledButton(onPressed: _apply, child: const Text('Search')),
            OutlinedButton(
              onPressed: _clear,
              child: const Text('Clear filters'),
            ),
            OutlinedButton.icon(
              onPressed: _list.loading ? null : _list.refresh,
              icon: const Icon(Icons.refresh_outlined),
              label: const Text('Refresh'),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            OutlinedButton(
              onPressed: () => _pickDate(true),
              child: Text('From: ${_from == null ? 'Any' : _date(_from!)}'),
            ),
            OutlinedButton(
              onPressed: () => _pickDate(false),
              child: Text('To: ${_to == null ? 'Any' : _date(_to!)}'),
            ),
            if (_from != null || _to != null)
              TextButton(
                onPressed: () {
                  setState(() {
                    _from = null;
                    _to = null;
                  });
                },
                child: const Text('Clear dates'),
              ),
          ],
        ),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          key: ValueKey(_sort),
          initialValue: _sort,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Sort'),
          items: const [
            DropdownMenuItem(value: '-id', child: Text('Newest created')),
            DropdownMenuItem(value: 'id', child: Text('Oldest created')),
            DropdownMenuItem(
              value: '-audit_date',
              child: Text('Newest audit date'),
            ),
            DropdownMenuItem(
              value: 'audit_date',
              child: Text('Oldest audit date'),
            ),
          ],
          onChanged: (sort) {
            if (sort != null) {
              _sort = sort;
              _apply();
            }
          },
        ),
        if (_validation case final message?)
          StatusMessage(message, error: true),
        if (_filtered)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Semantics(
              label: 'Applied filters',
              child: Text(
                'Applied: ${[if (_list.query.driverName != null) 'Driver: ${_list.query.driverName}', if (_list.query.plateNumber != null) 'Plate: ${_list.query.plateNumber}', if (_list.query.station != null) 'Station: ${_list.query.station}', if (_list.query.dateFrom != null) 'From ${_list.query.dateFrom}', if (_list.query.dateTo != null) 'To ${_list.query.dateTo}'].join(' · ')}',
              ),
            ),
          ),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) {
    final page = _list.page;
    return Scaffold(
      appBar: AppBar(
        title: const Text('BHLI Audit'),
        actions: [
          IconButton(
            tooltip: 'Settings',
            onPressed: widget.onSettings,
            icon: const Icon(Icons.settings_outlined),
          ),
        ],
      ),
      body: SafeArea(
        child: ContentWidth(
          child: RefreshIndicator(
            onRefresh: _list.refresh,
            child: CustomScrollView(
              controller: _scroll,
              physics: const AlwaysScrollableScrollPhysics(),
              slivers: [
                SliverToBoxAdapter(child: _filters()),
                if (_list.loading)
                  const SliverToBoxAdapter(
                    child: Padding(
                      padding: EdgeInsets.all(16),
                      child: LinearProgressIndicator(
                        semanticsLabel: 'Loading audits',
                      ),
                    ),
                  ),
                if (_list.stale)
                  const SliverToBoxAdapter(
                    child: Padding(
                      padding: EdgeInsets.symmetric(horizontal: 16),
                      child: StatusMessage(
                        'Not refreshed. Displayed audits may be out of date.',
                        error: true,
                      ),
                    ),
                  ),
                if (_list.error case final message?)
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          StatusMessage(message, error: true),
                          OutlinedButton(
                            onPressed: _list.loading
                                ? null
                                : () => _list.apply(_list.query),
                            child: const Text('Retry'),
                          ),
                        ],
                      ),
                    ),
                  ),
                if (!_list.loading &&
                    _list.error == null &&
                    (page == null || page.items.isEmpty))
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        children: [
                          Text(
                            _filtered
                                ? 'No audits match these filters.'
                                : 'No audits available.',
                          ),
                          if (_filtered)
                            TextButton(
                              onPressed: _clear,
                              child: const Text('Clear filters'),
                            ),
                          if (_list.query.page > 1)
                            TextButton(
                              onPressed: _list.refresh,
                              child: const Text('Reload from page 1'),
                            ),
                        ],
                      ),
                    ),
                  ),
                if (page != null)
                  SliverList(
                    delegate: SliverChildBuilderDelegate((context, index) {
                      final record = page.items[index];
                      return Padding(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 4,
                        ),
                        child: Card(
                          clipBehavior: Clip.antiAlias,
                          child: InkWell(
                            onTap: () => Navigator.of(context).push(
                              MaterialPageRoute<void>(
                                builder: (_) => AuditDetailsScreen(
                                  session: widget.session,
                                  auditId: record.id,
                                  onSaved: _afterSaved,
                                  onVisibilityChanged: _list.refresh,
                                ),
                              ),
                            ),
                            child: Padding(
                              padding: const EdgeInsets.all(16),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    record.driverName,
                                    style: Theme.of(context)
                                        .textTheme
                                        .titleMedium,
                                  ),
                                  const SizedBox(height: 8),
                                  Text(
                                    '${record.auditDate} · ${record.station}',
                                  ),
                                  Text('Plate: ${record.plateNumber}'),
                                  const SizedBox(height: 4),
                                  const Text('View audit details'),
                                ],
                              ),
                            ),
                          ),
                        ),
                      );
                    }, childCount: page.items.length),
                  ),
                if (page != null)
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Wrap(
                        alignment: WrapAlignment.center,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        spacing: 16,
                        runSpacing: 12,
                        children: [
                          OutlinedButton(
                            onPressed: _list.loading || _list.query.page <= 1
                                ? null
                                : _list.previous,
                            child: const Text('Previous'),
                          ),
                          Text(
                            'Page ${_list.query.page} of ${page.totalPages} · ${page.total} audits',
                          ),
                          OutlinedButton(
                            onPressed:
                                _list.loading ||
                                    _list.query.page >= page.totalPages ||
                                    _list.query.page >= 10000
                                ? null
                                : _list.next,
                            child: const Text('Next'),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
