import 'dart:async';

import 'package:bhli_audit/offline/app.dart';
import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/repository.dart';
import 'package:bhli_audit/offline/sqlite_repository.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

// Real SQLite backs normal widget flows. This boundary decorator injects only
// delayed I/O and failures that cannot be exercised deterministically by taps.
class ControlledRepository implements OfflineRepository {
  ControlledRepository(this.inner);
  final OfflineRepository inner;
  Completer<void>? createGate;
  bool failCreateAfterCommit = false;
  bool failList = false;
  bool failRead = false;
  bool failHistory = false;
  bool failProfile = false;
  @override
  Future<LocalProfile?> profile() async {
    if (failProfile) throw StateError('private /database/path');
    return inner.profile();
  }

  @override
  Future<LocalProfile> saveProfile(String name) => inner.saveProfile(name);
  @override
  Future<AuditPage> list(AuditFilter filter) async {
    if (failList) throw StateError('private /database/path');
    return inner.list(filter);
  }

  @override
  Future<LocalAudit> read(String id) async {
    if (failRead) throw StateError('private /database/path');
    return inner.read(id);
  }

  @override
  Future<LocalAudit> create(String id, AuditValues values) async {
    await createGate?.future;
    final result = await inner.create(id, values);
    if (failCreateAfterCommit) {
      failCreateAfterCommit = false;
      throw StateError('private /database/path');
    }
    return result;
  }

  @override
  Future<LocalAudit> update(String id, int revision, AuditValues values) =>
      inner.update(id, revision, values);
  @override
  Future<LocalAudit> archive(String id, int revision) =>
      inner.archive(id, revision);
  @override
  Future<List<LocalEvent>> history(
    String id, {
    int page = 1,
    int pageSize = 10,
  }) async {
    if (failHistory) throw StateError('private /database/path');
    return inner.history(id, page: page, pageSize: pageSize);
  }

  @override
  Future<void> close() => inner.close();
}

AuditValues values(String driver) => AuditValues(
  driverName: driver,
  helperName: 'Fictional Helper',
  auditDate: '2026-11-05',
  station: 'Fictional Station',
  plateNumber: 'TEST-123',
  remarks: 'Fictional only',
);

Future<void> tap(WidgetTester tester, String text) async {
  final finder = find.text(text).last;
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

Future<void> enter(WidgetTester tester, String key, String text) async {
  final finder = find.byKey(ValueKey(key));
  await tester.ensureVisible(finder);
  await tester.enterText(finder, text);
  await tester.pump();
}

Future<void> fill(
  WidgetTester tester, {
  String driver = 'Fictional Driver',
}) async {
  await enter(tester, 'offline_driver_name', driver);
  await enter(tester, 'offline_helper_name', 'Fictional Helper');
  await enter(tester, 'offline_audit_date', '2026-11-05');
  await enter(tester, 'offline_station', 'Fictional Station');
  await enter(tester, 'offline_plate_number', 'TEST-123');
  await enter(tester, 'offline_remarks', 'Fictional only');
}

void offlineTestWidgets(
  String description,
  Future<void> Function(WidgetTester) body,
) {
  testWidgets(description, (tester) async {
    await tester.runAsync(() => body(tester));
  });
}

void main() {
  sqfliteFfiInit();
  late SqliteOfflineRepository db;
  late ControlledRepository repository;
  setUp(() async {
    db = await SqliteOfflineRepository.open(
      inMemoryDatabasePath,
      factory: databaseFactoryFfiNoIsolate,
    );
    repository = ControlledRepository(db);
  });
  tearDown(() async => db.close());
  Future<void> launch(WidgetTester tester, {bool profile = true}) async {
    if (profile) await db.saveProfile('Fictional Auditor');
    await tester.pumpWidget(OfflineApp(repository: repository));
    await tester.pumpAndSettle();
  }

  // Catches bypassed profile validation and accidental initial record seeding.
  offlineTestWidgets(
    'fresh setup rejects blank and overlong names before empty list',
    (tester) async {
      await launch(tester, profile: false);
      await tap(tester, 'Start offline');
      expect(await db.profile(), isNull);
      await enter(tester, 'offline_profile_name', 'a' * 201);
      await tap(tester, 'Start offline');
      expect(await db.profile(), isNull);
      await enter(tester, 'offline_profile_name', 'a' * 200);
      await tap(tester, 'Start offline');
      expect((await db.profile())!.name.length, 200);
      expect(find.text('No audits yet'), findsOneWidget);
      expect(find.textContaining('Back up regularly'), findsWidgets);
      expect(find.textContaining('no backup'), findsNothing);
    },
  );

  // Catches dropped form fields, mutable original creator and lost event views.
  offlineTestWidgets(
    'create edit rename history and archive preserve original auditor',
    (tester) async {
      await launch(tester);
      await tap(tester, 'New Audit');
      await fill(tester);
      await tap(tester, 'Save');
      expect(find.text('Audit saved'), findsOneWidget);
      final created = (await db.list(const AuditFilter())).items.single;
      expect(created.values.helperName, 'Fictional Helper');
      expect(created.values.remarks, 'Fictional only');
      await tester.tap(find.byTooltip('Local profile'));
      await tester.pumpAndSettle();
      await enter(tester, 'offline_profile_name', 'Renamed Fictional Auditor');
      await tap(tester, 'Save');
      await tap(tester, 'Fictional Driver');
      await tap(tester, 'Edit Audit');
      expect(find.text('Fictional Auditor'), findsWidgets);
      await enter(tester, 'offline_driver_name', 'Updated Fictional Driver');
      await tap(tester, 'Save');
      await tap(tester, 'History');
      expect(find.textContaining('Renamed Fictional Auditor'), findsWidgets);
      expect(find.textContaining('Fictional Driver'), findsWidgets);
      await tester.pageBack();
      await tester.pumpAndSettle();
      await tap(tester, 'Archive Audit');
      await tap(tester, 'Archive');
      expect((await db.read(created.id)).archived, isTrue);
      expect((await db.read(created.id)).auditedByName, 'Fictional Auditor');
      expect((await db.history(created.id)).length, 3);
    },
  );

  // Catches page size/offset errors and filters being discarded after a save.
  offlineTestWidgets(
    'list pages 25 records and applies filters and four sorts',
    (tester) async {
      await db.saveProfile('Fictional Auditor');
      for (var i = 0; i < 26; i++) {
        await db.create(
          newUuid(),
          values('Fictional ${i.toString().padLeft(2, '0')}'),
        );
      }
      await launch(tester, profile: false);
      expect(find.text('Fictional 25'), findsOneWidget);
      expect(find.text('Fictional 00'), findsNothing);
      await tap(tester, 'Next');
      expect(find.text('Fictional 00'), findsOneWidget);
      await tap(tester, 'Previous');
      await tap(tester, 'Filters');
      await enter(tester, 'offline_filter_driver', 'Fictional 00');
      await enter(tester, 'offline_filter_plate', 'TEST');
      await enter(tester, 'offline_filter_station', 'Fictional');
      await enter(tester, 'offline_filter_date_from', '2026-11-01');
      await enter(tester, 'offline_filter_date_to', '2026-11-30');
      await tap(tester, 'Apply filters');
      expect(find.text('Fictional 00'), findsOneWidget);
      expect(find.text('Fictional 25'), findsNothing);
      for (final sort in [
        'Oldest created',
        'Audit date newest',
        'Audit date oldest',
        'Newest created',
      ]) {
        await tester.ensureVisible(find.byKey(const ValueKey('offline_sort')));
        await tester.tap(find.byKey(const ValueKey('offline_sort')));
        await tester.pumpAndSettle();
        await tap(tester, sort);
        expect(find.text('Fictional 00'), findsOneWidget);
      }
      await tap(tester, 'New Audit');
      await fill(tester, driver: 'Does not match');
      await tap(tester, 'Save');
      expect(find.text('Audit saved'), findsOneWidget);
      expect(find.text('Fictional 00'), findsOneWidget);
      expect(find.text('Does not match'), findsNothing);
    },
  );

  // Catches leaving an admitted transaction and duplicate dispatch on rapid taps.
  offlineTestWidgets(
    'dirty cancel asks and pending save blocks double save and navigation',
    (tester) async {
      await launch(tester);
      await tap(tester, 'New Audit');
      await fill(tester);
      await tap(tester, 'Cancel');
      expect(find.text('Discard changes?'), findsOneWidget);
      await tap(tester, 'Keep editing');
      repository.createGate = Completer<void>();
      await tester.ensureVisible(find.text('Save'));
      await tester.tap(find.text('Save'));
      await tester.tap(find.text('Save'));
      await tester.pump();
      await tester.pageBack();
      await tester.pump();
      expect(find.textContaining('Keep this screen open'), findsOneWidget);
      expect(find.text('Create Audit'), findsOneWidget);
      repository.createGate!.complete();
      await tester.pumpAndSettle();
      expect((await db.list(const AuditFilter())).total, 1);
      expect(
        (await db.history((await db.list(const AuditFilter())).items.single.id))
            .length,
        1,
      );
    },
  );

  // Catches a committed-but-unconfirmed create remaining hidden after dismissal.
  offlineTestWidgets(
    'review regression uncertain discard reloads committed audit without false success',
    (tester) async {
      await launch(tester);
      expect(find.text('No audits yet'), findsOneWidget);
      await tap(tester, 'New Audit');
      await fill(tester);
      repository.failCreateAfterCommit = true;
      await tap(tester, 'Save');
      await tap(tester, 'Cancel');
      await tap(tester, 'Discard changes');
      expect(find.text('Fictional Driver'), findsOneWidget);
      expect(find.text('No audits yet'), findsNothing);
      expect(find.text('Audit saved'), findsNothing);
      expect((await db.list(const AuditFilter())).total, 1);
    },
  );

  // Catches navigation skipping a page after an unsuccessful Next or Previous.
  offlineTestWidgets(
    'review regression failed pagination keeps controls on the loaded page',
    (tester) async {
      await db.saveProfile('Fictional Auditor');
      for (var i = 0; i < 51; i++) {
        await db.create(
          newUuid(),
          values('Fictional ${i.toString().padLeft(2, '0')}'),
        );
      }
      await launch(tester, profile: false);
      repository.failList = true;
      await tap(tester, 'Next');
      expect(find.text('Page 1 \u00b7 51 audits'), findsOneWidget);
      expect(find.text('Fictional 50'), findsOneWidget);
      expect(
        tester
            .widget<OutlinedButton>(
              find.widgetWithText(OutlinedButton, 'Previous'),
            )
            .onPressed,
        isNull,
      );
      expect(
        tester
            .widget<OutlinedButton>(find.widgetWithText(OutlinedButton, 'Next'))
            .onPressed,
        isNotNull,
      );
      repository.failList = false;
      await tap(tester, 'Next');
      expect(find.text('Page 2 \u00b7 51 audits'), findsOneWidget);
      expect(find.text('Fictional 25'), findsOneWidget);
      expect(find.text('Fictional 00'), findsNothing);
      repository.failList = true;
      await tap(tester, 'Previous');
      expect(find.text('Page 2 \u00b7 51 audits'), findsOneWidget);
      expect(
        tester
            .widget<OutlinedButton>(
              find.widgetWithText(OutlinedButton, 'Previous'),
            )
            .onPressed,
        isNotNull,
      );
      repository.failList = false;
      await tap(tester, 'Previous');
      expect(find.text('Page 1 \u00b7 51 audits'), findsOneWidget);
      expect(find.text('Fictional 50'), findsOneWidget);
    },
  );

  // Catches dropping the failed request when loaded and requested state separate.
  offlineTestWidgets(
    'review regression retry requests the failed page instead of the loaded page',
    (tester) async {
      await db.saveProfile('Fictional Auditor');
      for (var i = 0; i < 26; i++) {
        await db.create(
          newUuid(),
          values('Fictional ${i.toString().padLeft(2, '0')}'),
        );
      }
      await launch(tester, profile: false);
      repository.failList = true;
      await tap(tester, 'Next');
      expect(find.text('Page 1 \u00b7 26 audits'), findsOneWidget);
      expect(
        tester
            .widget<OutlinedButton>(find.widgetWithText(OutlinedButton, 'Next'))
            .onPressed,
        isNotNull,
      );
      repository.failList = false;
      await tap(tester, 'Retry');
      expect(find.text('Page 2 \u00b7 26 audits'), findsOneWidget);
      expect(find.text('Fictional 00'), findsOneWidget);
    },
  );

  // Catches failed filter/sort choices being presented as already applied.
  offlineTestWidgets(
    'review regression failed filters and sorts retain loaded selection until retry succeeds',
    (tester) async {
      await db.saveProfile('Fictional Auditor');
      await db.create(newUuid(), values('Alpha Fictional Driver'));
      await db.create(newUuid(), values('Beta Fictional Driver'));
      await launch(tester, profile: false);
      await tap(tester, 'Filters');
      await enter(tester, 'offline_filter_driver', 'Alpha');
      repository.failList = true;
      await tap(tester, 'Apply filters');
      expect(find.text('Alpha Fictional Driver'), findsOneWidget);
      expect(find.text('Beta Fictional Driver'), findsOneWidget);
      expect(find.text('Page 1 \u00b7 2 audits'), findsOneWidget);
      repository.failList = false;
      await tap(tester, 'Retry');
      expect(find.text('Alpha Fictional Driver'), findsOneWidget);
      expect(find.text('Beta Fictional Driver'), findsNothing);
      await tap(tester, 'Filters');
      await enter(tester, 'offline_filter_driver', '');
      await tap(tester, 'Apply filters');
      repository.failList = true;
      await tester.ensureVisible(find.byKey(const ValueKey('offline_sort')));
      await tester.tap(find.byKey(const ValueKey('offline_sort')));
      await tester.pumpAndSettle();
      await tap(tester, 'Oldest created');
      expect(find.text('Newest created'), findsOneWidget);
      expect(find.text('Oldest created'), findsNothing);
      repository.failList = false;
      await tap(tester, 'Retry');
      expect(find.text('Oldest created'), findsOneWidget);
      expect(
        tester.getTopLeft(find.text('Alpha Fictional Driver')).dy,
        lessThan(tester.getTopLeft(find.text('Beta Fictional Driver')).dy),
      );
    },
  );

  // Catches generating a fresh UUID or changing payload after an uncertain write.
  offlineTestWidgets(
    'uncertain committed create retries frozen attempt without duplicate',
    (tester) async {
      await launch(tester);
      await tap(tester, 'New Audit');
      await fill(tester);
      repository.failCreateAfterCommit = true;
      await tap(tester, 'Save');
      expect(find.text('Retry save'), findsOneWidget);
      expect(
        tester
            .widget<TextFormField>(
              find.byKey(const ValueKey('offline_driver_name')),
            )
            .enabled,
        isFalse,
      );
      expect(find.textContaining('/database/path'), findsNothing);
      await tap(tester, 'Retry save');
      expect(find.text('Audit saved'), findsOneWidget);
      expect((await db.list(const AuditFilter())).total, 1);
    },
  );

  // Catches presenting a committed write as failure when its list refresh fails.
  offlineTestWidgets(
    'confirmed save remains successful if list refresh fails',
    (tester) async {
      await launch(tester);
      await tap(tester, 'New Audit');
      await fill(tester);
      repository.failList = true;
      await tap(tester, 'Save');
      expect(find.text('Audit saved'), findsOneWidget);
      expect(find.textContaining('refresh'), findsWidgets);
      expect((await db.list(const AuditFilter())).total, 1);
      expect(find.textContaining('/database/path'), findsNothing);
      repository.failList = false;
      await tap(tester, 'Retry');
      expect(find.text('Fictional Driver'), findsOneWidget);
    },
  );

  // Catches silent stale revision overwrites and accidental conflict resubmission.
  offlineTestWidgets(
    'stale edit requires explicit discard and reload before saving',
    (tester) async {
      await db.saveProfile('Fictional Auditor');
      final original = await db.create(
        newUuid(),
        values('Original Fictional Driver'),
      );
      await launch(tester, profile: false);
      await tap(tester, 'Original Fictional Driver');
      await tap(tester, 'Edit Audit');
      await db.update(original.id, 1, values('Other Fictional Change'));
      await enter(tester, 'offline_driver_name', 'My stale change');
      await tap(tester, 'Save');
      expect(find.text('Discard changes and reload'), findsOneWidget);
      expect(
        (await db.read(original.id)).values.driverName,
        'Other Fictional Change',
      );
      await tap(tester, 'Discard changes and reload');
      expect(
        tester
            .widget<TextFormField>(
              find.byKey(const ValueKey('offline_driver_name')),
            )
            .controller!
            .text,
        'Other Fictional Change',
      );
      expect((await db.read(original.id)).revision, 2);
    },
  );

  // Catches raw errors, stuck loading states and read/history retry regressions.
  offlineTestWidgets(
    'startup read and history failures stay actionable and sanitized',
    (tester) async {
      repository.failProfile = true;
      await launch(tester);
      expect(find.text('Retry'), findsOneWidget);
      expect(find.textContaining('/database/path'), findsNothing);
      repository.failProfile = false;
      await tap(tester, 'Retry');
      final record = await db.create(newUuid(), values('Fictional Driver'));
      await tap(tester, 'Refresh');
      repository.failRead = true;
      await tap(tester, 'Fictional Driver');
      expect(find.text('Retry'), findsOneWidget);
      repository.failRead = false;
      await tap(tester, 'Retry');
      repository.failHistory = true;
      await tap(tester, 'History');
      expect(find.text('Retry'), findsOneWidget);
      repository.failHistory = false;
      await tap(tester, 'Retry');
      expect(find.textContaining('CREATE'), findsWidgets);
      expect((await db.history(record.id)).length, 1);
    },
  );

  // Catches callbacks updating disposed UI, without cancelling admitted writes.
  offlineTestWidgets('disposing during save allows storage to finish safely', (
    tester,
  ) async {
    await launch(tester);
    await tap(tester, 'New Audit');
    await fill(tester);
    repository.createGate = Completer<void>();
    await tester.ensureVisible(find.text('Save'));
    await tester.tap(find.text('Save'));
    await tester.pump();
    await tester.pumpWidget(const SizedBox());
    repository.createGate!.complete();
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect((await db.list(const AuditFilter())).total, 1);
  });

  // Catches invalid input reaching SQLite and missing accessible first-error focus.
  offlineTestWidgets(
    'six-field validation focuses first error and date picker preserves valid input',
    (tester) async {
      await launch(tester);
      await tap(tester, 'New Audit');
      await tap(tester, 'Save');
      expect(find.text('Check these fields before saving:'), findsOneWidget);
      expect(
        tester
            .widget<EditableText>(
              find.descendant(
                of: find.byKey(const ValueKey('offline_driver_name')),
                matching: find.byType(EditableText),
              ),
            )
            .focusNode
            .hasFocus,
        isTrue,
      );
      expect((await db.list(const AuditFilter())).total, 0);
      await fill(tester);
      for (final entry in {
        'driver_name': 200,
        'helper_name': 200,
        'station': 150,
        'plate_number': 30,
        'remarks': 10000,
      }.entries) {
        await enter(tester, 'offline_${entry.key}', 'a' * (entry.value + 1));
        await tap(tester, 'Save');
        expect((await db.list(const AuditFilter())).total, 0);
        await fill(tester);
      }
      await enter(tester, 'offline_audit_date', '2026-02-30');
      await tap(tester, 'Save');
      expect((await db.list(const AuditFilter())).total, 0);
      await enter(tester, 'offline_audit_date', '2024-02-29');
      await tester.ensureVisible(find.byTooltip('Choose audit date'));
      await tester.tap(find.byTooltip('Choose audit date'));
      await tester.pumpAndSettle();
      expect(find.byType(DatePickerDialog), findsOneWidget);
      await tap(tester, 'OK');
      await tap(tester, 'Save');
      expect(
        (await db.list(const AuditFilter())).items.single.values.auditDate,
        '2024-02-29',
      );
    },
  );

  // Catches stale on-screen creator labels being mistaken for mutable attribution.
  offlineTestWidgets(
    'a renamed profile is captured at create while existing original stays immutable',
    (tester) async {
      await launch(tester);
      await tap(tester, 'New Audit');
      await fill(tester);
      await db.saveProfile('Current Fictional Auditor');
      expect(
        find.textContaining('current profile name when saved'),
        findsOneWidget,
      );
      await tap(tester, 'Save');
      final record = (await db.list(const AuditFilter())).items.single;
      expect(record.auditedByName, 'Current Fictional Auditor');
      await tap(tester, 'Fictional Driver');
      await tap(tester, 'Edit Audit');
      expect(find.text('Current Fictional Auditor'), findsOneWidget);
      await db.saveProfile('Newest Fictional Auditor');
      await enter(tester, 'offline_station', 'Edited Fictional Station');
      await tap(tester, 'Save');
      expect(
        (await db.read(record.id)).auditedByName,
        'Current Fictional Auditor',
      );
      expect(
        (await db.history(record.id)).first.actorName,
        'Newest Fictional Auditor',
      );
    },
  );

  // Catches history page offsets skipping events and editable archived records.
  offlineTestWidgets(
    'archived audit remains readable and history pages without skipped events',
    (tester) async {
      await db.saveProfile('Fictional Auditor');
      var record = await db.create(newUuid(), values('Fictional Driver'));
      for (var i = 0; i < 11; i++) {
        record = await db.update(
          record.id,
          record.revision,
          values('Fictional Driver $i'),
        );
      }
      await db.archive(record.id, record.revision);
      await launch(tester, profile: false);
      expect(find.text('No audits yet'), findsOneWidget);
      await tap(tester, 'Include archived');
      await tap(tester, 'Fictional Driver 10');
      expect(find.text('Edit Audit'), findsNothing);
      expect(find.text('Archive Audit'), findsNothing);
      await tap(tester, 'History');
      expect(find.text('ARCHIVE \u00b7 Revision 13'), findsOneWidget);
      expect(find.text('CREATE \u00b7 Revision 1'), findsNothing);
      await tap(tester, 'Next');
      expect(find.text('CREATE \u00b7 Revision 1'), findsOneWidget);
      expect(find.text('UPDATE \u00b7 Revision 3'), findsOneWidget);
      await tap(tester, 'Previous');
      expect(find.text('ARCHIVE \u00b7 Revision 13'), findsOneWidget);
    },
  );

  // Catches archive conflicts silently using the latest revision to overwrite.
  offlineTestWidgets(
    'stale archive reloads only after an explicit choice and second confirmation',
    (tester) async {
      await db.saveProfile('Fictional Auditor');
      final original = await db.create(newUuid(), values('Fictional Driver'));
      await launch(tester, profile: false);
      await tap(tester, 'Fictional Driver');
      await db.update(original.id, 1, values('Other Fictional Driver'));
      await tap(tester, 'Archive Audit');
      await tap(tester, 'Archive');
      expect(find.text('Reload latest audit'), findsOneWidget);
      expect((await db.read(original.id)).archived, isFalse);
      await tap(tester, 'Reload latest audit');
      expect(find.text('Other Fictional Driver'), findsOneWidget);
      expect((await db.read(original.id)).archived, isFalse);
      await tap(tester, 'Archive Audit');
      await tap(tester, 'Archive');
      expect((await db.read(original.id)).archived, isTrue);
    },
  );

  // Catches losing the save result when Android system Back closes the details.
  offlineTestWidgets(
    'system back after editing resets list page and reports saved audit',
    (tester) async {
      await db.saveProfile('Fictional Auditor');
      for (var i = 0; i < 26; i++) {
        await db.create(newUuid(), values('Fictional $i'));
      }
      await launch(tester, profile: false);
      await tap(tester, 'Next');
      await tap(tester, 'Fictional 0');
      await tap(tester, 'Edit Audit');
      await enter(tester, 'offline_station', 'Changed Fictional Station');
      await tap(tester, 'Save');
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.text('Page 1 \u00b7 26 audits'), findsOneWidget);
      expect(find.text('Audit saved'), findsOneWidget);
    },
  );

  // Catches clipping fixed form actions in landscape with a visible keyboard.
  offlineTestWidgets('landscape 200 percent form saves with keyboard visible', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(640, 320);
    tester.view.devicePixelRatio = 1;
    tester.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    addTearDown(tester.view.resetViewInsets);
    await launch(tester);
    await tap(tester, 'New Audit');
    await fill(tester);
    tester.view.viewInsets = const FakeViewPadding(bottom: 120);
    await tester.pumpAndSettle();
    await tap(tester, 'Save');
    expect(find.text('Audit saved'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  for (final brightness in Brightness.values) {
    // Catches fixed-width actions/labels and keyboard-obscured form controls.
    offlineTestWidgets(
      'compact 200 percent ${brightness.name} form stays usable with keyboard',
      (tester) async {
        tester.view.physicalSize = const Size(320, 640);
        tester.view.devicePixelRatio = 1;
        tester.platformDispatcher.textScaleFactorTestValue = 2;
        tester.platformDispatcher.platformBrightnessTestValue = brightness;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
        await launch(tester);
        await tap(tester, 'New Audit');
        await fill(tester);
        tester.view.viewInsets = const FakeViewPadding(bottom: 240);
        await tester.pumpAndSettle();
        await tap(tester, 'Save');
        expect(find.text('Audit saved'), findsOneWidget);
        expect(tester.takeException(), isNull);
        tester.view.resetViewInsets();
      },
    );
  }
}
