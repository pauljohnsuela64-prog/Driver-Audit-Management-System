import 'package:flutter/material.dart';

import '../ui/core/audit_theme.dart';
import '../ui/core/content.dart';
import 'details.dart';
import 'form.dart';
import 'models.dart';
import 'repository.dart';

const offlineDevelopmentWarning =
    'Development: fictional data only. This device has no backup. Uninstalling or clearing app data can permanently remove local audits.';

/// Injected repositories belong to the caller; production bootstrap owns shutdown.
class OfflineApp extends StatefulWidget {
  const OfflineApp({super.key, required this.repository});
  final OfflineRepository repository;
  @override
  State<OfflineApp> createState() => _OfflineAppState();
}

class _OfflineAppState extends State<OfflineApp> {
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'BHLI Audit Offline',
    theme: auditTheme(Brightness.light),
    darkTheme: auditTheme(Brightness.dark),
    home: _OfflineHome(repository: widget.repository),
  );
}

class _OfflineHome extends StatefulWidget {
  const _OfflineHome({required this.repository});
  final OfflineRepository repository;
  @override
  State<_OfflineHome> createState() => _OfflineHomeState();
}

class _OfflineHomeState extends State<_OfflineHome> {
  LocalProfile? profile;
  bool starting = true;
  bool loading = false;
  String? startupError;
  String? error;
  String? success;
  AuditPage? result;
  AuditFilter filter = const AuditFilter();
  AuditFilter? failedRequest;
  bool filtersOpen = false;
  final filterForm = GlobalKey<FormState>();
  final driver = TextEditingController();
  final plate = TextEditingController();
  final station = TextEditingController();
  final dateFrom = TextEditingController();
  final dateTo = TextEditingController();
  @override
  void initState() {
    super.initState();
    start();
  }

  Future<void> start() async {
    setState(() {
      starting = true;
      startupError = null;
    });
    try {
      final local = await widget.repository.profile();
      if (!mounted) return;
      setState(() => profile = local);
    } catch (failure) {
      if (mounted) {
        setState(
          () => startupError = offlineError(
            failure,
            operation: 'open your local profile',
          ),
        );
      }
    } finally {
      if (mounted) setState(() => starting = false);
    }
    if (mounted && startupError == null && profile != null) await load();
  }

  Future<void> load({bool resetPage = false, AuditFilter? request}) async {
    if (loading) return;
    final requested = request ?? (resetPage ? changeFilter(page: 1) : filter);
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final page = await widget.repository.list(requested);
      if (mounted) {
        setState(() {
          filter = requested;
          result = page;
          failedRequest = null;
        });
      }
    } catch (failure) {
      if (mounted) {
        setState(() {
          failedRequest = requested;
          error = offlineError(failure, operation: 'refresh the audit list');
        });
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  AuditFilter changeFilter({int? page, String? sort, bool? includeArchived}) =>
      AuditFilter(
        driver: filter.driver,
        plate: filter.plate,
        station: filter.station,
        dateFrom: filter.dateFrom,
        dateTo: filter.dateTo,
        includeArchived: includeArchived ?? filter.includeArchived,
        sort: sort ?? filter.sort,
        page: page ?? filter.page,
        pageSize: 25,
      );

  Future<void> applyFilters() async {
    if (loading || !filterForm.currentState!.validate()) return;
    if (dateFrom.text.isNotEmpty &&
        dateTo.text.isNotEmpty &&
        dateFrom.text.compareTo(dateTo.text) > 0) {
      setState(
        () => error = 'The start date must be on or before the end date.',
      );
      return;
    }
    final requested = AuditFilter(
      driver: driver.text.trim(),
      plate: plate.text.trim(),
      station: station.text.trim(),
      dateFrom: dateFrom.text.isEmpty ? null : dateFrom.text,
      dateTo: dateTo.text.isEmpty ? null : dateTo.text,
      sort: filter.sort,
      includeArchived: filter.includeArchived,
      pageSize: 25,
    );
    setState(() => filtersOpen = false);
    await load(request: requested);
  }

  Future<void> newAudit() async {
    if (loading) return;
    LocalProfile? current;
    setState(() {
      loading = true;
      error = null;
      success = null;
    });
    try {
      current = await widget.repository.profile();
      if (current == null) {
        throw const OfflineFailure('profile', 'Profile unavailable');
      }
      if (mounted) setState(() => profile = current);
    } catch (failure) {
      if (mounted) {
        setState(
          () => error = offlineError(
            failure,
            operation: 'load your local profile',
          ),
        );
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
    if (!mounted || current == null) return;
    final saved = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (_) =>
            OfflineAuditForm(repository: widget.repository, profile: current!),
      ),
    );
    if (!mounted) return;
    if (saved == true) setState(() => success = 'Audit saved');
    // A dismissed attempt may have committed before confirmation failed.
    // Reload page one with the same filters, without claiming a confirmed save.
    await load(resetPage: true);
  }

  Future<void> openAudit(String id) async {
    final changed = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (_) =>
            OfflineAuditDetails(repository: widget.repository, id: id),
      ),
    );
    if (!mounted) return;
    if (changed == true) setState(() => success = 'Audit saved');
    await load(resetPage: changed == true);
  }

  Future<void> settings() async {
    if (profile == null) return;
    final updated = await Navigator.push<LocalProfile>(
      context,
      MaterialPageRoute(
        builder: (_) => _LocalProfileScreen(
          repository: widget.repository,
          profile: profile,
        ),
      ),
    );
    if (mounted && updated != null) setState(() => profile = updated);
  }

  Widget filterField(
    String key,
    String label,
    TextEditingController controller, {
    bool date = false,
  }) => Padding(
    padding: const EdgeInsets.only(bottom: 16),
    child: TextFormField(
      key: ValueKey('offline_filter_$key'),
      controller: controller,
      decoration: InputDecoration(
        labelText: label,
        errorMaxLines: 3,
        helperText: date ? 'YYYY-MM-DD (optional)' : null,
      ),
      validator: (value) =>
          date && value != null && value.isNotEmpty && !validOfflineDate(value)
          ? 'Enter a valid date as YYYY-MM-DD.'
          : null,
    ),
  );

  @override
  Widget build(BuildContext context) {
    if (starting || startupError != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('BHLI Audit Offline')),
        body: SafeArea(
          child: ContentWidth(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (starting) const LinearProgressIndicator(),
                  if (startupError != null) ...[
                    StatusMessage(startupError!, error: true),
                    OutlinedButton(
                      onPressed: start,
                      child: const Text('Retry'),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      );
    }
    if (profile == null) {
      return _LocalProfileScreen(
        repository: widget.repository,
        onSetup: (saved) async {
          setState(() => profile = saved);
          await load();
        },
      );
    }
    final hasFilters =
        filter.driver.isNotEmpty ||
        filter.plate.isNotEmpty ||
        filter.station.isNotEmpty ||
        filter.dateFrom != null ||
        filter.dateTo != null;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Audits'),
        actions: [
          IconButton(
            tooltip: 'Local profile',
            onPressed: settings,
            icon: const Icon(Icons.person_outline),
          ),
        ],
      ),
      body: SafeArea(
        child: ContentWidth(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(offlineDevelopmentWarning),
                const SizedBox(height: 16),
                Text('Local profile: ${profile!.name} (self-declared)'),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 16,
                  runSpacing: 8,
                  children: [
                    FilledButton(
                      onPressed: loading ? null : newAudit,
                      child: const Text('New Audit'),
                    ),
                    OutlinedButton(
                      onPressed: loading
                          ? null
                          : () => setState(() => filtersOpen = !filtersOpen),
                      child: const Text('Filters'),
                    ),
                    OutlinedButton(
                      onPressed: loading ? null : load,
                      child: const Text('Refresh'),
                    ),
                  ],
                ),
                if (success != null) StatusMessage(success!),
                if (loading) const LinearProgressIndicator(),
                if (error != null) ...[
                  StatusMessage(error!, error: true),
                  if (result != null)
                    const Text(
                      'Showing the last loaded results. Retry applies the requested page, filters, and sort.',
                    ),
                  OutlinedButton(
                    onPressed: loading
                        ? null
                        : () => load(request: failedRequest),
                    child: const Text('Retry'),
                  ),
                ],
                const SizedBox(height: 16),
                if (filtersOpen)
                  Form(
                    key: filterForm,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        filterField('driver', 'Driver search', driver),
                        filterField('plate', 'Plate search', plate),
                        filterField('station', 'Station search', station),
                        filterField(
                          'date_from',
                          'Date from',
                          dateFrom,
                          date: true,
                        ),
                        filterField('date_to', 'Date to', dateTo, date: true),
                        OutlinedButton(
                          onPressed: loading ? null : applyFilters,
                          child: const Text('Apply filters'),
                        ),
                        const SizedBox(height: 16),
                      ],
                    ),
                  ),
                InputDecorator(
                  decoration: const InputDecoration(labelText: 'Sort audits'),
                  child: DropdownButtonHideUnderline(
                    child: DropdownButton<String>(
                      key: const ValueKey('offline_sort'),
                      value: filter.sort,
                      isExpanded: true,
                      items: const [
                        DropdownMenuItem(
                          value: '-created',
                          child: Text('Newest created'),
                        ),
                        DropdownMenuItem(
                          value: 'created',
                          child: Text('Oldest created'),
                        ),
                        DropdownMenuItem(
                          value: '-audit_date',
                          child: Text('Audit date newest'),
                        ),
                        DropdownMenuItem(
                          value: 'audit_date',
                          child: Text('Audit date oldest'),
                        ),
                      ],
                      onChanged: loading
                          ? null
                          : (value) {
                              if (value != null) {
                                load(
                                  request: changeFilter(sort: value, page: 1),
                                );
                              }
                            },
                    ),
                  ),
                ),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Include archived'),
                  value: filter.includeArchived,
                  onChanged: loading
                      ? null
                      : (value) {
                          load(
                            request: changeFilter(
                              includeArchived: value,
                              page: 1,
                            ),
                          );
                        },
                ),
                if (result != null &&
                    result!.items.isEmpty &&
                    error == null &&
                    !loading)
                  StatusMessage(
                    hasFilters
                        ? 'No audits match these filters'
                        : 'No audits yet',
                  ),
                if (result != null)
                  for (final record in result!.items)
                    Card(
                      child: InkWell(
                        onTap: loading ? null : () => openAudit(record.id),
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Text(
                                record.values.driverName,
                                style: Theme.of(context).textTheme.titleMedium,
                              ),
                              Text(
                                '${record.values.plateNumber} · ${record.values.station}',
                              ),
                              Text(record.values.auditDate),
                              Text('Audited By: ${record.auditedByName}'),
                              if (record.archived) const Text('Archived'),
                            ],
                          ),
                        ),
                      ),
                    ),
                if (result != null) ...[
                  const SizedBox(height: 16),
                  Text('Page ${result!.page} · ${result!.total} audits'),
                  Wrap(
                    spacing: 16,
                    runSpacing: 8,
                    children: [
                      OutlinedButton(
                        onPressed: loading || filter.page <= 1
                            ? null
                            : () {
                                load(
                                  request: changeFilter(page: filter.page - 1),
                                );
                              },
                        child: const Text('Previous'),
                      ),
                      OutlinedButton(
                        onPressed: loading || filter.page * 25 >= result!.total
                            ? null
                            : () {
                                load(
                                  request: changeFilter(page: filter.page + 1),
                                );
                              },
                        child: const Text('Next'),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    for (final controller in [driver, plate, station, dateFrom, dateTo]) {
      controller.dispose();
    }
    super.dispose();
  }
}

class _LocalProfileScreen extends StatefulWidget {
  const _LocalProfileScreen({
    required this.repository,
    this.profile,
    this.onSetup,
  });
  final OfflineRepository repository;
  final LocalProfile? profile;
  final ValueChanged<LocalProfile>? onSetup;
  @override
  State<_LocalProfileScreen> createState() => _LocalProfileScreenState();
}

class _LocalProfileScreenState extends State<_LocalProfileScreen> {
  final form = GlobalKey<FormState>();
  late final TextEditingController name;
  bool busy = false;
  String? error;
  @override
  void initState() {
    super.initState();
    name = TextEditingController(text: widget.profile?.name ?? '');
  }

  Future<void> save() async {
    if (busy || !form.currentState!.validate()) return;
    setState(() {
      busy = true;
      error = null;
    });
    LocalProfile? saved;
    try {
      saved = await widget.repository.saveProfile(name.text);
    } catch (failure) {
      if (mounted) {
        setState(
          () => error = offlineError(
            failure,
            operation: 'save your local profile',
          ),
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
    if (!mounted || saved == null) return;
    if (widget.onSetup != null) {
      widget.onSetup!(saved);
    } else {
      Navigator.pop(context, saved);
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !busy,
    child: Scaffold(
      appBar: AppBar(
        title: Text(
          widget.profile == null ? 'Set up local profile' : 'Local profile',
        ),
        automaticallyImplyLeading: !busy,
      ),
      body: SafeArea(
        child: ContentWidth(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Form(
              key: form,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(offlineDevelopmentWarning),
                  const SizedBox(height: 24),
                  const Text(
                    'Your name is self-declared and recorded with new audits. Changing it affects future creations only; original auditor names stay unchanged.',
                  ),
                  const SizedBox(height: 24),
                  TextFormField(
                    key: const ValueKey('offline_profile_name'),
                    controller: name,
                    enabled: !busy,
                    decoration: const InputDecoration(
                      labelText: 'Your name',
                      errorMaxLines: 3,
                    ),
                    validator: (value) {
                      try {
                        offlineText(value ?? '', 200);
                        return null;
                      } on OfflineFailure {
                        return (value ?? '').trim().isEmpty
                            ? 'Enter your name.'
                            : 'Use 200 characters or fewer.';
                      }
                    },
                    textInputAction: TextInputAction.done,
                    onFieldSubmitted: (_) => save(),
                  ),
                  if (error != null) StatusMessage(error!, error: true),
                  if (busy)
                    const StatusMessage(
                      'Saving locally. Keep this screen open until the operation finishes.',
                    ),
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: busy ? null : save,
                    child: Text(
                      busy
                          ? 'Saving…'
                          : widget.profile == null
                          ? 'Start offline'
                          : 'Save',
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    ),
  );
  @override
  void dispose() {
    name.dispose();
    super.dispose();
  }
}
