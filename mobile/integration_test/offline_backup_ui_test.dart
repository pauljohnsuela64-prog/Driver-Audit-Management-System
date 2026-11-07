// Fictional Android UI acceptance target only. Never publish this test APK.
import 'dart:async';
import 'dart:io';

import 'package:bhli_audit/offline/app.dart';
import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/sqlite_repository.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:sqflite/sqflite.dart';

class _NoNetwork extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) =>
      throw StateError('Fictional backup UI acceptance forbids HTTP');
}

const _phrase = 'Fictional acceptance phrase only 2026';
const _run = String.fromEnvironment('DAMS_BACKUP_ACCEPTANCE_RUN');

Future<void> _until(WidgetTester tester, bool Function() ready) async {
  final deadline = DateTime.now().add(const Duration(minutes: 8));
  while (!ready()) {
    if (DateTime.now().isAfter(deadline)) {
      throw TimeoutException('Fictional acceptance stage timed out');
    }
    await tester.pump(const Duration(milliseconds: 100));
    await Future<void>.delayed(const Duration(milliseconds: 100));
  }
  await tester.pump();
}

Future<void> _text(WidgetTester tester, String text) =>
    _until(tester, () => find.textContaining(text).evaluate().isNotEmpty);

Future<void> _tap(WidgetTester tester, Finder finder) async {
  await _until(tester, () => finder.evaluate().isNotEmpty);
  await tester.ensureVisible(finder.last);
  await tester.tap(finder.last);
  await tester.pump();
}

Future<void> _capture(WidgetTester tester, String name) async {
  // Activity recreation can restore FLAG_SECURE. Re-enable fictional capture
  // only at non-password checkpoints, never in the ordinary application target.
  // The background checkpoint deliberately exercises the real resume behavior.
  if (name != 'background-form-cleared') {
    await const MethodChannel('com.bhli.audit/privacy')
        .invokeMethod<void>('setSecure', {'secure': false});
  }
  debugPrint('PHASE6E_UI_CAPTURE $name');
  await _until(
    tester,
    () => Directory(
      '/data/user/0/com.bhli.audit.offline/files/phase6e-ui-$_run-$name.ack',
    ).existsSync(),
  );
}

Future<void> _password(
  WidgetTester tester, {
  bool confirm = true,
  String phrase = _phrase,
}) async {
  await _until(
    tester,
    () => find.byKey(const ValueKey('backup_password')).evaluate().isNotEmpty,
  );
  await tester.enterText(find.byKey(const ValueKey('backup_password')), phrase);
  if (confirm) {
    await tester.enterText(
      find.byKey(const ValueKey('backup_confirmation')),
      phrase,
    );
  }
  await _tap(tester, find.text('Continue'));
}

Future<void> _openBackup(WidgetTester tester, String stage) async {
  debugPrint('PHASE6E_UI_SAF OPEN $stage');
  await _tap(tester, find.text('Restore Backup'));
  if (stage == 'preview-cancel') {
    await _password(
      tester,
      confirm: false,
      phrase: 'Fictional incorrect phrase only',
    );
    await _text(tester, 'Cannot unlock this backup.');
    expect(find.text('Authenticated replacement preview'), findsNothing);
    debugPrint('PHASE6E_UI_WRONG_PASSWORD_PASS');
  }
  await _password(tester, confirm: false);
  await _text(tester, 'Authenticated replacement preview');
}

Future<void> _prepare(WidgetTester tester, String stage) async {
  await _tap(tester, find.text('Save required recovery backup'));
  debugPrint('PHASE6E_UI_SAF SAVE $stage');
  await _password(tester);
  await _text(
    tester,
    'Recovery backup saved and authenticated from destination readback.',
  );
  await _tap(tester, find.byType(CheckboxListTile));
  await _tap(tester, find.text("Replace this device's data"));
  await _text(tester, "Replace this device's data?");
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  if (!validOfflineUuid(_run)) {
    throw StateError('Supply a fresh fictional acceptance run UUID');
  }
  testWidgets(
    'real OfflineApp encrypted backup SAF and confirmed replacement',
    (tester) async {
      HttpOverrides.global = _NoNetwork();
      final directory = Directory(
        '${await getDatabasesPath()}/acceptance6e-ui-$_run',
      );
      if (await directory.exists()) {
        throw StateError('Refusing reused fixture directory');
      }
      await directory.create();
      final appPath = '${await getDatabasesPath()}/bhli_offline.db';
      if (await File(appPath).exists()) {
        throw StateError('Refusing existing app database');
      }
      final repo = await SqliteOfflineRepository.open(appPath);
      // The detached fictional sender uses real sqflite explicitly; only the
      // actual app target opens the normal path and owns the default native lease.
      final origin = await SqliteOfflineRepository.open(
        '${directory.path}/origin.db',
        factory: databaseFactory,
      );
      try {
        // Real app, native SQLite and its default native data-directory lease.
        runApp(OfflineApp(repository: repo));
        await _text(tester, 'Backup & restore');
        await _tap(tester, find.text('Backup & restore'));
        await _text(tester, 'Create Backup');
        // Debug-only capture override; ordinary APK privacy is verified separately.
        await const MethodChannel('com.bhli.audit/privacy')
            .invokeMethod<void>('setSecure', {'secure': false});
        await _capture(tester, 'empty-setup');
        await _tap(tester, find.text('Create Backup'));
        await tester.enterText(
          find.byKey(const ValueKey('backup_password')),
          _phrase,
        );
        await _capture(tester, 'background-form-cleared');
        await _text(tester, 'Create Backup');
        expect(find.byKey(const ValueKey('backup_password')), findsNothing);
        await _tap(tester, find.byType(BackButton));
        await repo.saveProfile('Fictional UI Recipient');
        await origin.saveProfile('Fictional Original Auditor');
        final id = newUuid();
        AuditValues values(String station) => AuditValues(
          driverName: 'Fictional Jos\u00e9 \u674e',
          helperName: 'Fictional Helper',
          auditDate: '2026-11-07',
          station: station,
          plateNumber: '00047',
          remarks: 'Fictional backup UI acceptance only',
        );
        await origin.create(id, values('Fictional Original Station'));
        await origin.saveProfile('Fictional Renamed Auditor');
        await origin.update(id, 1, values('Fictional Edited Station'));
        await origin.archive(id, 2);
        final transferred = await origin.exportTransfer();
        await repo.applyTransfer(
          transferred,
          await repo.previewTransfer(transferred),
        );
        final backedUp = await repo.captureBackup();
        // Rebuild the real app after seeding to refresh its saved profile.
        await tester.pumpWidget(const SizedBox.shrink());
        runApp(OfflineApp(repository: repo));
        await _until(
          tester,
          () => find.byTooltip('Local profile').evaluate().isNotEmpty,
        );
        await _tap(tester, find.byTooltip('Local profile'));
        await _tap(tester, find.text('Backup & restore'));
        await _tap(tester, find.text('Create Backup'));
        debugPrint('PHASE6E_UI_SAF SAVE backup');
        await _password(tester);
        await _text(
          tester,
          'Encrypted complete backup saved and authenticated',
        );
        expect(tester.takeException(), isNull);
        await _capture(tester, 'backup-saved');

        await repo.create(newUuid(), values('Fictional Later Local Record'));
        final before = await repo.captureBackup();
        debugPrint('PHASE6E_UI_SAF CANCEL picker-cancel');
        await _tap(tester, find.text('Restore Backup'));
        await _text(tester, 'Create Backup');
        expect((await repo.captureBackup()).digest, before.digest);
        await _openBackup(tester, 'preview-cancel');
        await _capture(tester, 'preview-light');
        await _capture(tester, 'preview-dark-compact200');
        await _prepare(tester, 'recovery-cancel');
        await _capture(tester, 'confirmation-cancel');
        final cancel = find.descendant(
          of: find.byType(AlertDialog),
          matching: find.text('Cancel'),
        );
        expect(
          tester
              .widget<TextButton>(
                find.ancestor(of: cancel, matching: find.byType(TextButton)),
              )
              .autofocus,
          true,
        );
        await _tap(tester, cancel);
        await _text(
          tester,
          'Replacement cancelled. The complete original state is unchanged.',
        );
        expect((await repo.captureBackup()).digest, before.digest);

        await _openBackup(tester, 'restore-confirm');
        await _prepare(tester, 'recovery-confirm');
        await _tap(
          tester,
          find.descendant(
            of: find.byType(AlertDialog),
            matching: find.text("Replace this device's data"),
          ),
        );
        await _text(tester, 'The complete backup was restored and verified.');
        expect((await repo.captureBackup()).digest, backedUp.digest);
        expect((await repo.profile())!.name, 'Fictional UI Recipient');
        expect(
          (await repo.read(id)).auditedByName,
          'Fictional Original Auditor',
        );
        expect((await repo.read(id)).archived, true);
        expect((await repo.history(id)).length, 3);
        expect(
          (await repo.captureBackup()).rows['transfer_receipts'],
          backedUp.rows['transfer_receipts'],
        );
        await _capture(tester, 'restored-profile-refresh');
        debugPrint('PHASE6E_UI_PASS $_run');
      } finally {
        await tester.pumpWidget(const SizedBox.shrink());
        await origin.close();
        await repo.close();
        HttpOverrides.global = null;
        await const MethodChannel('com.bhli.audit/privacy')
            .invokeMethod<void>('setSecure', {'secure': true});
      }
    },
    timeout: const Timeout(Duration(minutes: 45)),
  );
}
