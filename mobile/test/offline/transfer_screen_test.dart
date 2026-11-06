import 'dart:io';

import 'package:flutter/services.dart';

import 'package:bhli_audit/offline/transfer_screen.dart';
import 'package:bhli_audit/offline/transfer_documents.dart';
import 'package:bhli_audit/offline/sqlite_repository.dart';
import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/ui/core/audit_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

class LocalDocuments extends TransferDocuments {
  int saves = 0;
  bool failSave = false;
  @override
  Future<String?> pickImport() async =>
      'test/fixtures/transfer/python-v1.bhlitransfer';
  @override
  Future<Uint8List> readStage(String path) async =>
      File(path).readAsBytesSync();
  @override
  Future<String> stage(Uint8List bytes) async => '/private/prepared';
  @override
  Future<bool> saveStage(String path, String name) async {
    saves++;
    if (failSave) {
      throw PlatformException(
        code: 'cleanup_incomplete',
        message: '/private/location SQL',
      );
    }
    return true;
  }

  @override
  Future<void> deleteStage(String path) async {}
}

void main() {
  late SqliteOfflineRepository repo;
  setUp(() async {
    sqfliteFfiInit();
    repo = await SqliteOfflineRepository.open(
      inMemoryDatabasePath,
      factory: databaseFactoryFfiNoIsolate,
    );
    await repo.saveProfile('Local Auditor');
  });
  tearDown(() async => repo.close());
  transferTestWidgets(
    'import previews new records and requires an explicit import confirmation',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OfflineTransferScreen(
            repository: repo,
            importing: true,
            documents: LocalDocuments(),
          ),
        ),
      );
      await tester.tap(find.text('Choose transfer file'));
      await settleTransfer(tester);
      expect(find.text('New: 1'), findsOneWidget);
      expect((await repo.list(const AuditFilter())).total, 0);
      await tester.tap(find.text('Import new records only'));
      await settleTransfer(tester);
      expect(find.textContaining('Imported 1'), findsOneWidget);
      expect((await repo.list(const AuditFilter())).total, 1);
      expect((await repo.profile())!.name, 'Local Auditor');
    },
  );
  transferTestWidgets(
    'different versions require acknowledgment and remain unchanged',
    (tester) async {
      final bytes = File('test/fixtures/transfer/python-v1.bhlitransfer')
          .readAsBytesSync();
      final preview = await repo.previewTransfer(bytes);
      await repo.applyTransfer(bytes, preview);
      final original = (await repo.list(const AuditFilter())).items.single;
      final edited = await repo.update(
        original.id,
        original.revision,
        AuditValues(
          driverName: 'Local edit',
          auditDate: original.values.auditDate,
          station: original.values.station,
          plateNumber: original.values.plateNumber,
        ),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: OfflineTransferScreen(
            repository: repo,
            importing: true,
            documents: LocalDocuments(),
          ),
        ),
      );
      await tester.tap(find.text('Choose transfer file'));
      await settleTransfer(tester);
      expect(find.text('Different version: 1'), findsOneWidget);
      final button = find.widgetWithText(
        FilledButton,
        'Import new records only',
      );
      expect(tester.widget<FilledButton>(button).onPressed, isNull);
      await tester.tap(find.byType(CheckboxListTile));
      await tester.pump();
      await tester.ensureVisible(button);
      await tester.tap(button);
      await settleTransfer(tester);
      expect((await repo.read(original.id)).revision, edited.revision);
      expect((await repo.read(original.id)).values.driverName, 'Local edit');
    },
  );
  transferTestWidgets(
    'failed provider cleanup warns about an incomplete file without exposing internals',
    (tester) async {
      final docs = LocalDocuments()..failSave = true;
      await tester.pumpWidget(
        MaterialApp(
          home: OfflineTransferScreen(repository: repo, documents: docs),
        ),
      );
      await tester.tap(find.text('Prepare export'));
      await settleTransfer(tester);
      await tester.tap(
        find.widgetWithText(OutlinedButton, 'Choose destination'),
      );
      await settleTransfer(tester);
      expect(
        find.textContaining('An incomplete file may remain'),
        findsOneWidget,
      );
      expect(find.text('Transfer saved.'), findsNothing);
      expect(find.textContaining('/private/location'), findsNothing);
    },
  );
  transferTestWidgets(
    'empty export shows prepared snapshot count before creating a destination',
    (tester) async {
      final docs = LocalDocuments();
      await tester.pumpWidget(
        MaterialApp(
          home: OfflineTransferScreen(repository: repo, documents: docs),
        ),
      );
      await tester.tap(find.text('Prepare export'));
      await settleTransfer(tester);
      expect(
        find.text('0 audits prepared, including archived records.'),
        findsOneWidget,
      );
      expect(docs.saves, 0);
      await tester.tap(
        find.widgetWithText(OutlinedButton, 'Choose destination'),
      );
      await settleTransfer(tester);
      expect(find.text('Transfer saved.'), findsOneWidget);
      expect(docs.saves, 1);
    },
  );
  for (final brightness in [Brightness.light, Brightness.dark]) {
    transferTestWidgets(
      'compact 200 percent ${brightness.name} date-range export stays usable',
      (tester) async {
        tester.view.physicalSize = const Size(320, 640);
        tester.view.devicePixelRatio = 1;
        tester.platformDispatcher.textScaleFactorTestValue = 2;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        addTearDown(tester.view.resetViewInsets);
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        for (final date in ['2026-11-05', '2026-11-06']) {
          await repo.create(
            newUuid(),
            AuditValues(
              driverName: 'Fictional Unicode \u674e',
              auditDate: date,
              station: 'North',
              plateNumber: '00047',
            ),
          );
        }
        await tester.pumpWidget(
          MaterialApp(
            theme: auditTheme(brightness),
            home: OfflineTransferScreen(
              repository: repo,
              documents: LocalDocuments(),
            ),
          ),
        );
        await tester.ensureVisible(find.byType(CheckboxListTile));
        await tester.tap(find.byType(CheckboxListTile));
        await tester.pumpAndSettle();
        await tester.ensureVisible(find.byType(TextFormField).first);
        await tester.enterText(find.byType(TextFormField).first, '2026-11-06');
        await tester.ensureVisible(find.byType(TextFormField).last);
        await tester.enterText(find.byType(TextFormField).last, '2026-11-06');
        tester.view.viewInsets = const FakeViewPadding(bottom: 220);
        await tester.pumpAndSettle();
        await tester.ensureVisible(find.text('Prepare export'));
        await tester.tap(find.text('Prepare export'));
        await settleTransfer(tester);
        expect(
          find.text('1 audits prepared, including archived records.'),
          findsOneWidget,
        );
        expect(tester.takeException(), isNull);
        await tester.ensureVisible(find.text('Close'));
        await tester.tap(find.text('Close'));
        await tester.pumpAndSettle();
      },
    );
  }
}

Future<void> settleTransfer(WidgetTester tester) async {
  for (var i = 0; i < 300; i++) {
    await tester.pump(const Duration(milliseconds: 10));
    await Future<void>.delayed(const Duration(milliseconds: 10));
    if (find.byType(LinearProgressIndicator).evaluate().isEmpty) {
      await tester.pumpAndSettle();
      return;
    }
  }
  fail('Transfer did not finish');
}

void transferTestWidgets(
  String description,
  Future<void> Function(WidgetTester) body,
) {
  testWidgets(description, (tester) async {
    await tester.runAsync(() => body(tester));
  });
}
