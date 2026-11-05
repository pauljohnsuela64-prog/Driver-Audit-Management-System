// Fictional native test target only. Never bundle or publish this APK.
import 'dart:io';

import 'package:bhli_audit/offline/app.dart';
import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/sqlite_repository.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:sqflite/sqflite.dart';

class NoNetwork extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) =>
      throw StateError('Offline native acceptance must not request HTTP');
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => HttpOverrides.global = NoNetwork());
  tearDown(() => HttpOverrides.global = null);

  Future<void> waitFor(WidgetTester tester, Finder finder) async {
    for (var i = 0; i < 100; i++) {
      await tester.pump(const Duration(milliseconds: 100));
      if (finder.evaluate().isNotEmpty) return;
      await Future<void>.delayed(const Duration(milliseconds: 50));
    }
    expect(finder, findsWidgets);
  }

  testWidgets(
    'native empty profile and offline CRUD survives database reopen',
    (tester) async {
      // Unique test-owned database; never the ordinary app's bhli_offline.db.
      final path = '${await getDatabasesPath()}/acceptance-${newUuid()}.db';
      var repository = await SqliteOfflineRepository.open(path);
      try {
        expect(await repository.profile(), isNull);
        expect((await repository.list(const AuditFilter())).total, 0);
        await tester.pumpWidget(OfflineApp(repository: repository));
        await waitFor(tester, find.byKey(const Key('offline_profile_name')));
        await tester.enterText(
          find.byKey(const Key('offline_profile_name')),
          'Fictional Native Auditor',
        );
        await tester.ensureVisible(find.text('Start offline'));
        await tester.tap(find.text('Start offline'));
        await waitFor(tester, find.text('No audits yet'));
        expect(find.text('Connection setup'), findsNothing);
        expect(find.text('Sign in'), findsNothing);

        await tester.tap(find.text('New Audit').first);
        await waitFor(tester, find.byKey(const Key('offline_driver_name')));
        final input = {
          'driver_name': 'Fictional Native \u674e',
          'helper_name': '',
          'audit_date': '2026-11-05',
          'station': 'Fictional Native Station',
          'plate_number': '00047',
          'remarks': 'Fictional offline acceptance only',
        };
        for (final item in input.entries) {
          final field = find.byKey(Key('offline_${item.key}'));
          await tester.ensureVisible(field);
          await tester.enterText(field, item.value);
        }
        FocusManager.instance.primaryFocus?.unfocus();
        await tester.pumpAndSettle();
        await tester.ensureVisible(find.text('Save').last);
        await tester.tap(find.text('Save').last);
        await waitFor(tester, find.text('Fictional Native \u674e'));
        final record = (await repository.list(const AuditFilter()))
            .items
            .single;
        expect(record.values.plateNumber, '00047');
        expect(record.auditedByName, 'Fictional Native Auditor');
        await repository.saveProfile('Fictional Renamed Auditor');
        final updated = await repository.update(
          record.id,
          1,
          AuditValues(
            driverName: record.values.driverName,
            auditDate: record.values.auditDate,
            station: 'Fictional Edited Station',
            plateNumber: record.values.plateNumber,
            remarks: 'Edited while offline',
          ),
        );
        expect(updated.auditedByName, 'Fictional Native Auditor');
        expect(updated.revision, 2);
        await expectLater(
          repository.update(record.id, 1, updated.values),
          throwsA(isA<OfflineFailure>()),
        );
        await repository.archive(record.id, 2);
        expect((await repository.list(const AuditFilter())).total, 0);
        expect(
          (await repository.list(const AuditFilter(includeArchived: true)))
              .total,
          1,
        );
        expect(
          (await repository.history(record.id)).map((event) => event.action),
          ['ARCHIVE', 'UPDATE', 'CREATE'],
        );
        expect(
          (await repository.history(record.id)).first.actorName,
          'Fictional Renamed Auditor',
        );
        await tester.pumpWidget(const SizedBox.shrink());
        await repository.close();
        repository = await SqliteOfflineRepository.open(path);
        expect((await repository.read(record.id)).archived, true);
        expect((await repository.history(record.id)).length, 3);
        expect((await repository.profile())!.name, 'Fictional Renamed Auditor');
      } finally {
        await tester.pumpWidget(const SizedBox.shrink());
        await repository.close();
        // Only this explicitly allocated fictional fixture is removed.
        await deleteDatabase(path);
        HttpOverrides.global = null;
      }
    },
  );

  testWidgets(
    'native local data persists across two independent app processes',
    (tester) async {
      const runId = String.fromEnvironment('DAMS_OFFLINE_ACCEPTANCE_RUN');
      expect(
        validOfflineUuid(runId),
        true,
        reason: 'Supply a new test-owned run UUID',
      );
      final path = '${await getDatabasesPath()}/acceptance-restart-$runId.db';
      final repository = await SqliteOfflineRepository.open(path);
      var secondProcess = false;
      try {
        final profile = await repository.profile();
        if (profile == null) {
          await repository.saveProfile('Fictional Restart Auditor');
          final record = await repository.create(
            newUuid(),
            AuditValues(
              driverName: 'Fictional Restart Driver',
              auditDate: '2026-11-05',
              station: 'Fictional Restart Station',
              plateNumber: '00084',
            ),
          );
          await repository.update(
            record.id,
            1,
            AuditValues(
              driverName: record.values.driverName,
              auditDate: record.values.auditDate,
              station: 'Fictional Persisted Station',
              plateNumber: '00084',
            ),
          );
          debugPrint('PHASE6B_RESTART_FIRST $runId');
        } else {
          secondProcess = true;
          expect(profile.name, 'Fictional Restart Auditor');
          final page = await repository.list(const AuditFilter());
          expect(page.total, 1);
          final record = page.items.single;
          expect(record.values.station, 'Fictional Persisted Station');
          expect(record.values.plateNumber, '00084');
          expect(record.revision, 2);
          expect((await repository.history(record.id)).length, 2);
          expect(record.auditedByName, 'Fictional Restart Auditor');
          debugPrint('PHASE6B_RESTART_SECOND $runId');
        }
      } finally {
        await repository.close();
        if (secondProcess) await deleteDatabase(path);
      }
    },
  );
}
