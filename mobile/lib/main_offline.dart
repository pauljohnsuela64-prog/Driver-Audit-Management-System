import 'dart:async';

import 'package:flutter/material.dart';
import 'package:sqflite/sqflite.dart';

import 'offline/app.dart';
import 'offline/models.dart';
import 'offline/repository.dart';
import 'offline/sqlite_repository.dart';
import 'ui/core/audit_theme.dart';
import 'ui/core/content.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const OfflineBootstrap());
}

/// Owns the production connection; tests can supply an isolated opener.
class OfflineBootstrap extends StatefulWidget {
  const OfflineBootstrap({super.key, this.openRepository});
  final Future<OfflineRepository> Function()? openRepository;
  @override
  State<OfflineBootstrap> createState() => _OfflineBootstrapState();
}

class _OfflineBootstrapState extends State<OfflineBootstrap>
    with WidgetsBindingObserver {
  OfflineRepository? _repository;
  String? _error;
  bool _opening = false;
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_open());
  }

  Future<void> _open() async {
    if (_opening) return;
    final generation = ++_generation;
    setState(() {
      _opening = true;
      _error = null;
    });
    try {
      final repository =
          await (widget.openRepository?.call() ?? _openPrivate());
      if (!mounted || generation != _generation) {
        await repository.close();
        return;
      }
      setState(() => _repository = repository);
    } catch (error) {
      if (mounted && generation == _generation) {
        setState(
          () => _error = error is OfflineFailure && error.code == 'schema'
              ? 'This local database is not supported by this app. Your data was not reset.'
              : 'Local storage could not be opened. Your data was not reset. Check available space and retry.',
        );
      }
    } finally {
      if (mounted && generation == _generation) {
        setState(() => _opening = false);
      }
    }
  }

  Future<OfflineRepository> _openPrivate() async =>
      SqliteOfflineRepository.open(
        '${await getDatabasesPath()}/bhli_offline.db',
      );

  void _close() {
    _generation++;
    final repository = _repository;
    _repository = null;
    if (repository != null) {
      // close() drains admitted transactions. Process death is still handled by
      // SQLite recovery; neither a disposed screen nor cancellation is rollback.
      unawaited(repository.close().catchError((Object _) {}));
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.detached) _close();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_repository case final repository?) {
      return OfflineApp(repository: repository);
    }
    return MaterialApp(
      title: 'BHLI Audit Offline',
      theme: auditTheme(Brightness.light),
      darkTheme: auditTheme(Brightness.dark),
      home: Scaffold(
        appBar: AppBar(title: const Text('BHLI Audit Offline')),
        body: SafeArea(
          child: ContentWidth(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: _opening
                  ? const Center(
                      child: CircularProgressIndicator(
                        semanticsLabel: 'Opening local storage',
                      ),
                    )
                  : Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        StatusMessage(
                          _error ?? 'Local storage is unavailable.',
                          error: true,
                        ),
                        FilledButton(
                          onPressed: _open,
                          child: const Text('Retry'),
                        ),
                      ],
                    ),
            ),
          ),
        ),
      ),
    );
  }
}
