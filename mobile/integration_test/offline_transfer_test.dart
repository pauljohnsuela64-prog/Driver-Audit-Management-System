// Fictional native acceptance target only. Never bundle or publish this APK.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/schema.dart';
import 'package:bhli_audit/offline/sqlite_repository.dart';
import 'package:bhli_audit/offline/transfer.dart';
import 'package:bhli_audit/offline/transfer_documents.dart';
import 'package:bhli_audit/offline/transfer_screen.dart';
import 'package:bhli_audit/ui/core/audit_theme.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:sqflite/sqflite.dart';

class _NoNetwork extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) =>
      throw StateError('Offline transfer acceptance must not request HTTP');
}

AuditValues _values([String station = 'Fictional Station']) => AuditValues(
  driverName: 'Fictional Jos\u00e9 \u674e \u{1f69a}',
  helperName: 'Fictional Helper',
  auditDate: '2026-11-06',
  station: station,
  plateNumber: '00047',
  remarks: 'Fictional native transfer acceptance only',
);

// Real time advances while Android's system picker owns the foreground.
Future<T> _native<T>(WidgetTester tester, Future<T> operation) async {
  var done = false;
  T? result;
  Object? failure;
  StackTrace? trace;
  operation.then(
    (value) {
      result = value;
      done = true;
    },
    onError: (Object error, StackTrace stack) {
      failure = error;
      trace = stack;
      done = true;
    },
  );
  final deadline = DateTime.now().add(const Duration(minutes: 5));
  while (!done && DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 50));
    await Future<void>.delayed(const Duration(milliseconds: 100));
  }
  if (!done) throw TimeoutException('Native transfer/picker did not complete');
  if (failure != null) Error.throwWithStackTrace(failure!, trace!);
  return result as T;
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => HttpOverrides.global = _NoNetwork());
  tearDown(() => HttpOverrides.global = null);

  // Register synchronously; this marker belongs only to the user-0 test package.
  final restartOnly = File(
    '/data/user/0/com.bhli.audit.offline/files/phase6d-restart-only-test',
  ).existsSync();
  testWidgets('native imported audits survive independent app processes', (
    tester,
  ) async {
    const run = String.fromEnvironment('DAMS_TRANSFER_ACCEPTANCE_RUN');
    expect(
      validOfflineUuid(run),
      true,
      reason: 'Use a unique fictional acceptance run UUID',
    );
    final root = await getDatabasesPath();
    final recipient = await SqliteOfflineRepository.open(
      '$root/acceptance6d-restart-$run.db',
    );
    try {
      final existing = await recipient.profile();
      if (existing == null) {
        await recipient.saveProfile('Fictional Restart Recipient');
        final sender = await SqliteOfflineRepository.open(
          '$root/acceptance6d-restart-source-$run.db',
        );
        try {
          await sender.saveProfile('Fictional Restart Origin');
          final record = await sender.create(newUuid(), _values());
          await sender.update(record.id, 1, _values('Changed before transfer'));
          await sender.archive(record.id, 2);
          final bytes = await sender.exportTransfer();
          await recipient.applyTransfer(
            bytes,
            await recipient.previewTransfer(bytes),
          );
        } finally {
          await sender.close();
        }
        debugPrint('PHASE6D_RESTART_FIRST');
      } else {
        expect(existing.name, 'Fictional Restart Recipient');
        final records = await recipient.list(
          const AuditFilter(includeArchived: true),
        );
        expect(records.total, 1);
        final record = records.items.single;
        expect(record.archived, true);
        expect(record.revision, 3);
        expect(record.auditedByName, 'Fictional Restart Origin');
        expect(record.values.plateNumber, '00047');
        expect(record.values.driverName, _values().driverName);
        expect((await recipient.history(record.id)).length, 3);
        debugPrint('PHASE6D_RESTART_SECOND');
      }
    } finally {
      await recipient.close();
    }
  });
  // A file in this test target's private storage selects only the restart
  // contract in a second instrumented process. Ordinary application code never
  // reads this marker or this acceptance database.
  if (restartOnly) return;

  testWidgets('native SQLite transfer and v1 migration preserve history', (
    tester,
  ) async {
    final root = await getDatabasesPath();
    final run = newUuid();
    final sourcePath = '$root/acceptance6d-source-$run.db';
    final targetPath = '$root/acceptance6d-target-$run.db';
    final legacyPath = '$root/acceptance6d-legacy-$run.db';
    final source = await SqliteOfflineRepository.open(sourcePath);
    var target = await SqliteOfflineRepository.open(targetPath);
    SqliteOfflineRepository? migrated;
    try {
      await source.saveProfile('Fictional Sender');
      await target.saveProfile('Fictional Recipient');
      final local = await target.profile();
      final id = newUuid();
      await source.create(id, _values());
      await source.saveProfile('Fictional Renamed Sender');
      await source.update(id, 1, _values('Fictional Edited Station'));
      await source.archive(id, 2);
      final raw = await source.exportTransfer();
      final package = await Isolate.run(() => decodeTransfer(raw));
      expect(package.audits.length, 1);
      expect(package.events.length, 3);
      final preview = await target.previewTransfer(raw);
      expect(preview.newIds, [id]);
      expect((await target.applyTransfer(raw, preview)).imported, 1);
      final again = await target.previewTransfer(raw);
      expect(again.duplicateIds, [id]);
      expect((await target.applyTransfer(raw, again)).imported, 0);
      expect((await target.profile())!.id, local!.id);
      expect((await target.profile())!.name, 'Fictional Recipient');
      expect((await target.read(id)).values.plateNumber, '00047');
      expect((await target.read(id)).values.driverName, _values().driverName);
      expect((await target.read(id)).auditedByName, 'Fictional Sender');
      final roundTrip = decodeTransfer(await target.exportTransfer());
      expect(canonicalJson(roundTrip.audits), canonicalJson(package.audits));
      expect(canonicalJson(roundTrip.events), canonicalJson(package.events));
      final other = newUuid();
      await target.create(other, _values('Fictional Return Station'));
      final back = await target.exportTransfer();
      final reverse = await source.previewTransfer(back);
      expect(reverse.newIds, [other]);
      expect(reverse.duplicateIds, [id]);
      expect((await source.applyTransfer(back, reverse)).imported, 1);
      await target.close();
      target = await SqliteOfflineRepository.open(targetPath);
      expect((await target.read(id)).archived, true);
      expect((await target.history(id)).map((e) => e.revision), [3, 2, 1]);
      expect((await target.previewTransfer(raw)).duplicateIds, [id]);

      // A newly allocated real v1 database, not a test factory or existing file.
      final legacy = await openDatabase(
        legacyPath,
        singleInstance: false,
        onConfigure: (db) => db.execute('PRAGMA foreign_keys = ON'),
      );
      try {
        await legacy.transaction((txn) async {
          for (final sql in offlineV1Tables.values) {
            await txn.execute(sql);
          }
          for (final sql in offlineIndexes.values) {
            await txn.execute(sql);
          }
          await txn.insert('app_meta', {
            'key': 'app_id',
            'value': 'com.bhli.audit.offline',
          });
          await txn.insert('app_meta', {
            'key': 'installation_id',
            'value': newUuid(),
          });
          await txn.insert('local_profile', {
            'singleton': 1,
            'id': package.audits.single['profile_id'],
            'name': 'Fictional Renamed Sender',
          });
          await txn.insert('audit_records', {
            'seq': 7,
            ...package.audits.single,
          });
          for (final event in package.events) {
            await txn.insert('audit_events', {
              for (final key in [
                'id',
                'audit_id',
                'revision',
                'action',
                'actor_name',
                'actor_profile_id',
                'created_at',
              ])
                key: event[key],
              'before_json': event['before'] == null
                  ? null
                  : canonicalJson(event['before']),
              'after_json': canonicalJson(event['after']),
            });
          }
          await txn.execute('PRAGMA user_version = 1');
        });
      } finally {
        await legacy.close();
      }
      migrated = await SqliteOfflineRepository.open(legacyPath);
      final upgraded = decodeTransfer(await migrated.exportTransfer());
      expect(canonicalJson(upgraded.audits), canonicalJson(package.audits));
      expect(canonicalJson(upgraded.events), canonicalJson(package.events));
      expect((await migrated.profile())!.name, 'Fictional Renamed Sender');
      await migrated.close();
      migrated = null;
      final inspect = await openDatabase(legacyPath, singleInstance: false);
      try {
        expect(
          (await inspect.rawQuery('PRAGMA user_version')).single.values.single,
          2,
        );
        expect((await inspect.query('audit_records')).single['seq'], 7);
        expect(await inspect.rawQuery('PRAGMA foreign_key_check'), isEmpty);
      } finally {
        await inspect.close();
      }
      debugPrint('PHASE6D_NATIVE_STORE_PASS $run');
    } finally {
      await source.close();
      await target.close();
      await migrated?.close();
      // Leave only uniquely allocated fictional acceptance files for inspection.
    }
  }, timeout: const Timeout(Duration(minutes: 10)));

  testWidgets('native document stages and actual SAF save open cancel', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Center(
            child: Text('Fictional Phase 6D native document acceptance'),
          ),
        ),
      ),
    );
    // Test-target screenshots only; production initialization remains untouched.
    await const MethodChannel('com.bhli.audit/privacy')
        .invokeMethod<void>('setSecure', {'secure': false});
    final repo = await SqliteOfflineRepository.open(
      '${await getDatabasesPath()}/acceptance6d-saf-${newUuid()}.db',
    );
    final docs = TransferDocuments();
    String? exportStage, importStage;
    try {
      await repo.saveProfile('Fictional SAF Sender');
      await repo.create(newUuid(), _values());
      final bytes = await repo.exportTransfer();
      exportStage = await docs.stage(bytes);
      expect(
        sha256.convert(await docs.readStage(exportStage)).toString(),
        sha256.convert(bytes).toString(),
      );
      debugPrint('PHASE6D_SAF_SAVE');
      expect(
        await _native(
          tester,
          docs.saveStage(exportStage, 'BHLI-audits.bhlitransfer'),
        ),
        true,
      );
      debugPrint('PHASE6D_SAF_OPEN');
      importStage = await _native(tester, docs.pickImport());
      expect(importStage, isNotNull);
      final imported = await docs.readStage(importStage!);
      expect(
        sha256.convert(imported).toString(),
        sha256.convert(bytes).toString(),
      );
      expect((await repo.previewTransfer(imported)).duplicateIds.length, 1);
      debugPrint('PHASE6D_SAF_CANCEL');
      expect(await _native(tester, docs.pickImport()), isNull);
      debugPrint('PHASE6D_NATIVE_SAF_PASS');
    } finally {
      if (exportStage != null) await docs.deleteStage(exportStage);
      if (importStage != null) await docs.deleteStage(importStage);
      await repo.close();
    }
  }, timeout: const Timeout(Duration(minutes: 20)));

  testWidgets('native transfer screens remain usable in both themes', (
    tester,
  ) async {
    final repo = await SqliteOfflineRepository.open(
      '${await getDatabasesPath()}/acceptance6d-ui-${newUuid()}.db',
    );
    try {
      await repo.saveProfile('Fictional UI Auditor');
      await repo.create(newUuid(), _values());
      for (final brightness in [Brightness.light, Brightness.dark]) {
        await tester.pumpWidget(
          MaterialApp(
            key: ValueKey(brightness),
            theme: auditTheme(brightness),
            home: OfflineTransferScreen(repository: repo),
          ),
        );
        await tester.pumpAndSettle();
        await tester.ensureVisible(find.text('Prepare export'));
        await tester.tap(find.text('Prepare export'));
        await _native(tester, () async {
          while (find
              .text('1 audits prepared, including archived records.')
              .evaluate()
              .isEmpty) {
            await Future<void>.delayed(const Duration(milliseconds: 50));
          }
        }());
        expect(tester.takeException(), isNull);
        debugPrint('PHASE6D_UI_${brightness.name.toUpperCase()}');
        await _native(tester, Future<void>.delayed(const Duration(seconds: 3)));
        await tester.ensureVisible(find.text('Close'));
        await tester.tap(find.text('Close'));
        await _native(
          tester,
          Future<void>.delayed(const Duration(milliseconds: 300)),
        );
      }
    } finally {
      await repo.close();
    }
  }, timeout: const Timeout(Duration(minutes: 3)));

  if (const bool.fromEnvironment('DAMS_TRANSFER_RESOURCE_PROBE')) {
    testWidgets('native near-ceiling transfer resource probe', (tester) async {
      final base = Directory(await getDatabasesPath()).parent.path;
      final file = File('$base/files/phase6d-resource.bhlitransfer');
      expect(
        await file.exists(),
        true,
        reason:
            'Stage the owned fictional resource fixture before instrumentation',
      );
      expect(await file.length(), lessThanOrEqualTo(32 * 1024 * 1024));
      final raw = Uint8List.fromList(await file.readAsBytes());
      final initial = ProcessInfo.currentRss;
      final watch = Stopwatch()..start();
      final package = await Isolate.run(() => decodeTransfer(raw));
      expect(package.audits.length, 2000);
      expect(package.events.length, 10000);
      const expectedDigest = String.fromEnvironment(
        'DAMS_TRANSFER_RESOURCE_SHA256',
      );
      expect(
        expectedDigest,
        matches(RegExp(r'^[0-9a-f]{64}$')),
        reason: 'Supply the fixture canonical content digest',
      );
      expect(package.contentSha256, expectedDigest);
      debugPrint(
        'PHASE6D_RESOURCE ${jsonEncode({'phase': 'decode', 'archive_bytes': raw.length, 'current_rss': ProcessInfo.currentRss, 'initial_rss': initial, 'max_rss': ProcessInfo.maxRss, 'elapsed_ms': watch.elapsedMilliseconds, 'content_sha256': package.contentSha256})}',
      );
      final resourcePath =
          '${await getDatabasesPath()}/acceptance6d-resource-${newUuid()}.db';
      final repository = await SqliteOfflineRepository.open(resourcePath);
      try {
        await repository.saveProfile('Fictional Resource Recipient');
        final preview = await repository.previewTransfer(raw);
        expect(preview.newIds.length, 2000);
        expect((await repository.applyTransfer(raw, preview)).imported, 2000);
        expect(
          (await repository.list(const AuditFilter(includeArchived: true)))
              .total,
          2000,
        );
        debugPrint(
          'PHASE6D_RESOURCE ${jsonEncode({'phase': 'import', 'current_rss': ProcessInfo.currentRss, 'max_rss': ProcessInfo.maxRss, 'elapsed_ms': watch.elapsedMilliseconds, 'database_bytes': await File(resourcePath).length()})}',
        );
      } finally {
        await repository.close();
      }
    }, timeout: const Timeout(Duration(minutes: 30)));
  }
}
