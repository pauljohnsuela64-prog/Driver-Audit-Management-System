import 'package:bhli_audit/offline/backup_screen.dart';
import 'package:bhli_audit/offline/app.dart';
import 'package:bhli_audit/offline/backup_store.dart';
import 'package:bhli_audit/offline/backup_documents.dart';
import 'package:bhli_audit/offline/backup_crypto.dart';
import 'package:bhli_audit/offline/sqlite_repository.dart';
import 'package:bhli_audit/offline/repository.dart';
import 'package:bhli_audit/offline/models.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'dart:io';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';

import 'backup_coordinator_test.dart' as fixtures;

class BlockedStartupRepository
    implements
        OfflineRepository,
        OfflineBackupRepository,
        OfflineRecoveryStatus {
  bool blocked = false;
  @override
  RestoreResult? startupRecovery;
  @override
  Future<LocalProfile?> profile() async {
    if (blocked) {
      throw const OfflineFailure(
        'maintenance',
        'Private internal storage details',
      );
    }
    return null;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

// These fakes record UI calls. Opaque objects are created by the actual core;
// coordinator tests separately enforce durable/AEAD proof and one-use tickets.
class ScreenStore implements BackupStore {
  late RestorePreview preview;
  late PreparedRestore ticket;
  late BackupArtifact artifact;
  int prepared = 0, applied = 0, abandoned = 0, requested = 0;
  RestoreOutcome outcome = RestoreOutcome.restored;
  Completer<RestoreResult>? applyGate;
  Completer<void>? abandonGate;
  @override
  Future<RestorePreview> inspectRestore(
    Uint8List bytes,
    String password, {
    bool Function()? cancel,
  }) async => preview;
  @override
  Future<BackupArtifact> createBackup(
    String password, {
    bool Function()? cancel,
  }) async => artifact;
  @override
  Future<PreparedRestore> prepareRestore(
    RestorePreview preview,
    String password, {
    required Future<Uint8List> Function(BackupArtifact) publishRecovery,
    bool Function()? cancel,
  }) async {
    await publishRecovery(artifact);
    prepared++;
    return ticket;
  }

  @override
  Future<RestoreResult> applyRestore(PreparedRestore ticket) async {
    applied++;
    return applyGate == null ? RestoreResult(outcome) : applyGate!.future;
  }

  @override
  Future<void> cancelPrepared(PreparedRestore ticket) async {
    abandoned++;
    await abandonGate?.future;
  }

  @override
  void cancelPreview(RestorePreview preview) {}
  @override
  void requestCancel(PreparedRestore ticket) {
    requested++;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class ScreenDocuments implements BackupDocuments {
  bool declineSave = false;
  int saved = 0;
  int cancellations = 0;
  Completer<String?>? saveGate;
  Completer<void>? cancelGate;
  @override
  Future<String?> pickBackup() async => 'selected';
  @override
  Future<String?> saveBackup(String handle, String name) async {
    saved++;
    return saveGate == null ? (declineSave ? null : 'saved') : saveGate!.future;
  }

  @override
  Future<void> cancel() async {
    cancellations++;
    await cancelGate?.future;
  }
}

class ScreenEvidence implements BackupEvidence {
  Uint8List? bytes;
  @override
  Future<Uint8List> read(String handle) async => bytes ?? Uint8List(1);
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  for (final action in ['Create Backup', 'Restore Backup']) {
    for (final lifecycle in [
      AppLifecycleState.inactive,
      AppLifecycleState.hidden,
      AppLifecycleState.paused,
      AppLifecycleState.detached,
    ]) {
      testWidgets('unsent $action passphrase is cleared on $lifecycle', (
        tester,
      ) async {
        final store = ScreenStore();
        await tester.pumpWidget(
          MaterialApp(
            home: OfflineBackupScreen(
              store: store,
              documents: ScreenDocuments(),
              evidence: ScreenEvidence(),
              onRestored: (_) {},
            ),
          ),
        );
        await tester.ensureVisible(find.text(action));
        await tester.tap(find.text(action));
        await tester.pumpAndSettle();
        final field = find.byKey(const ValueKey('backup_password'));
        await tester.enterText(field, fixtures.password);
        tester.binding.handleAppLifecycleStateChanged(lifecycle);
        await tester.pump();
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
        await tester.pumpAndSettle();
        expect(field, findsNothing);
        expect(find.text('Create Backup'), findsOneWidget);
        expect(store.applied, 0);
        expect(tester.takeException(), isNull);
      });
    }
  }

  testWidgets(
    'verified restore warning remains visible when rebuilt profile admission is blocked',
    (tester) async {
      tester.view.physicalSize = const Size(320, 640);
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      final repository = BlockedStartupRepository();
      await tester.pumpWidget(OfflineApp(repository: repository));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Backup & restore'));
      await tester.tap(find.text('Backup & restore'));
      await tester.pumpAndSettle();
      repository.blocked = true;
      final screen = tester.widget<OfflineBackupScreen>(
        find.byType(OfflineBackupScreen),
      );
      screen.onRestored(
        'The recovery marker could not be cleared. Local changes stay blocked. Retain all encrypted evidence.',
      );
      await tester.pumpAndSettle();
      expect(
        find.textContaining('The complete backup was restored and verified.'),
        findsOneWidget,
      );
      expect(
        find.textContaining('The recovery marker could not be cleared.'),
        findsOneWidget,
      );
      expect(
        find.textContaining('Private internal storage details'),
        findsNothing,
      );
      await tester.ensureVisible(find.text('Retry'));
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'known restored startup warning survives blocked profile admission',
    (tester) async {
      final repository = BlockedStartupRepository()
        ..blocked = true
        ..startupRecovery = const RestoreResult(
          RestoreOutcome.restored,
          warning: 'Retain the recovery marker and encrypted evidence.',
        );
      await tester.pumpWidget(OfflineApp(repository: repository));
      await tester.pumpAndSettle();
      expect(
        find.textContaining(
          'The complete restored state was verified after restart.',
        ),
        findsOneWidget,
      );
      expect(
        find.textContaining(
          'Retain the recovery marker and encrypted evidence.',
        ),
        findsOneWidget,
      );
    },
  );

  late RestorePreview preview;
  late PreparedRestore ticket;
  late BackupArtifact artifact;
  setUpAll(() async {
    sqfliteFfiInit();
    final dir = Directory.systemTemp.createTempSync('bhli-backup-ui-');
    final repo = await SqliteOfflineRepository.open(
      '${dir.path}/owned.db',
      factory: databaseFactoryFfi,
      ownership: fixtures.Ownership(),
    );
    try {
      final store = BackupStore(
        repo,
        evidence: fixtures.Evidence(),
        scratchFactory: databaseFactoryFfi,
      );
      final encrypted = await sealBackup(
        File('test/fixtures/backup/python-android-state.ndjson')
            .readAsBytesSync(),
        fixtures.password,
        platform: 'android',
      );
      preview = await store.inspectRestore(encrypted, fixtures.password);
      ticket = await store.prepareRestore(
        preview,
        fixtures.password,
        publishRecovery: (value) async {
          artifact = value;
          return value.bytes;
        },
      );
      await store.cancelPrepared(ticket);
    } finally {
      await repo.close();
      dir.deleteSync(recursive: true);
    }
  });
  Future<void> tap(WidgetTester tester, String text) async {
    await tester.ensureVisible(find.text(text).last);
    await tester.tap(find.text(text).last);
    await tester.pumpAndSettle();
  }

  Future<ScreenStore> preparedScreen(
    WidgetTester tester,
    ScreenDocuments documents, {
    ValueChanged<String>? restored,
    Brightness brightness = Brightness.light,
    double scale = 1,
  }) async {
    final store = ScreenStore()
      ..preview = preview
      ..ticket = ticket
      ..artifact = artifact;
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData(brightness: brightness),
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: TextScaler.linear(scale)),
          child: child!,
        ),
        home: OfflineBackupScreen(
          store: store,
          documents: documents,
          evidence: ScreenEvidence(),
          onRestored: restored ?? (_) {},
        ),
      ),
    );
    await tap(tester, 'Restore Backup');
    await tester.enterText(
      find.byKey(const ValueKey('backup_password')),
      fixtures.password,
    );
    await tap(tester, 'Continue');
    expect(find.text('Authenticated replacement preview'), findsOneWidget);
    expect(find.textContaining('Profile: none (empty setup)'), findsOneWidget);
    expect(store.prepared, 0);
    expect(find.text("Replace this device's data"), findsNothing);
    await tap(tester, 'Save required recovery backup');
    await tester.enterText(
      find.byKey(const ValueKey('backup_password')),
      fixtures.password,
    );
    await tester.enterText(
      find.byKey(const ValueKey('backup_confirmation')),
      fixtures.password,
    );
    await tap(tester, 'Continue');
    return store;
  }

  testWidgets('passphrase is exact and 15 to 128 characters', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: BackupPassphraseForm())),
    );
    await tester.enterText(
      find.byKey(const ValueKey('backup_password')),
      'too short',
    );
    await tester.tap(find.text('Continue'));
    await tester.pump();
    expect(find.text('Use 15 to 128 characters.'), findsOneWidget);
    await tester.enterText(
      find.byKey(const ValueKey('backup_password')),
      '  fifteen chars  ',
    );
    await tester.enterText(
      find.byKey(const ValueKey('backup_confirmation')),
      'fifteen chars',
    );
    await tester.tap(find.text('Continue'));
    await tester.pump();
    expect(find.text('The passphrases must match exactly.'), findsOneWidget);
  });

  testWidgets(
    'passphrase references clear before submit and accept exact spaces',
    (tester) async {
      String? submitted;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: BackupPassphraseForm(onSubmit: (value) => submitted = value),
          ),
        ),
      );
      const value = '  exact fictional passphrase  ';
      await tester.enterText(
        find.byKey(const ValueKey('backup_password')),
        value,
      );
      await tester.enterText(
        find.byKey(const ValueKey('backup_confirmation')),
        value,
      );
      await tap(tester, 'Continue');
      expect(submitted, value);
      for (final field in tester.widgetList<TextFormField>(
        find.byType(TextFormField),
      )) {
        expect(field.controller!.text, isEmpty);
      }
      await tester.enterText(
        find.byKey(const ValueKey('backup_password')),
        'x' * 129,
      );
      await tap(tester, 'Continue');
      expect(find.text('Use 15 to 128 characters.'), findsOneWidget);
    },
  );

  testWidgets('passphrase rejects control and malformed Unicode before work', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: BackupPassphraseForm())),
    );
    final validator = tester
        .widget<TextFormField>(find.byKey(const ValueKey('backup_password')))
        .validator!;
    expect(validator('fictional\npassphrase'), isNotNull);
    expect(validator('fictional\u007fpassphrase'), isNotNull);
    expect(
      validator('fictional${String.fromCharCode(0xd800)}passphrase'),
      isNotNull,
    );
    expect(validator('😀' * 128), isNull);
  });

  testWidgets(
    'empty setup offers backup and warns before discarding profile draft',
    (tester) async {
      late SqliteOfflineRepository repo;
      final dir = Directory.systemTemp.createTempSync(
        'bhli-backup-profile-ui-',
      );
      await tester.runAsync(() async {
        repo = await SqliteOfflineRepository.open(
          '${dir.path}/owned.db',
          factory: databaseFactoryFfi,
          ownership: fixtures.Ownership(),
        );
        repo.startupRecovery = const RestoreResult(
          RestoreOutcome.original,
          warning: 'Retain startup recovery evidence.',
        );
      });
      try {
        await tester.pumpWidget(OfflineApp(repository: repo));
        for (var i = 0; i < 15; i++) {
          await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 20)),
          );
          await tester.pump();
          if (find.text('Backup & restore').evaluate().isNotEmpty) break;
        }
        expect(find.text('Set up local profile'), findsOneWidget);
        expect(
          find.textContaining('Retain startup recovery evidence.'),
          findsOneWidget,
        );
        await tester.enterText(
          find.byKey(const ValueKey('offline_profile_name')),
          'Unfinished fictional draft',
        );
        await tap(tester, 'Backup & restore');
        expect(find.text('Discard unsaved profile changes?'), findsOneWidget);
        await tap(tester, 'Cancel');
        expect(find.byType(OfflineBackupScreen), findsNothing);
        await tap(tester, 'Backup & restore');
        await tap(tester, 'Discard draft and continue');
        expect(find.byType(OfflineBackupScreen), findsOneWidget);
        // Rebuilding MaterialApp erases the entire protected Navigator, including
        // profile drafts and every old route; home reads the same reopened owner.
        tester
            .widget<OfflineBackupScreen>(find.byType(OfflineBackupScreen))
            .onRestored('Retain encrypted evidence.');
        await tester.pump();
        for (var i = 0; i < 15; i++) {
          await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 20)),
          );
          await tester.pump();
          if (find.text('Set up local profile').evaluate().isNotEmpty) break;
        }
        expect(find.byType(OfflineBackupScreen), findsNothing);
        expect(find.text('Set up local profile'), findsOneWidget);
        expect(
          find.textContaining('Retain encrypted evidence.'),
          findsOneWidget,
        );
        expect(
          tester
              .widget<TextFormField>(
                find.byKey(const ValueKey('offline_profile_name')),
              )
              .controller!
              .text,
          isEmpty,
        );
        await tester.pumpWidget(const SizedBox());
      } finally {
        await tester.runAsync(repo.close);
        dir.deleteSync(recursive: true);
      }
    },
  );

  testWidgets(
    'mandatory saved recovery then acknowledgement and default Cancel',
    (tester) async {
      final documents = ScreenDocuments();
      final store = await preparedScreen(tester, documents);
      expect(documents.saved, 1);
      expect(store.prepared, 1);
      final replace = find.widgetWithText(
        FilledButton,
        "Replace this device's data",
      );
      expect(tester.widget<FilledButton>(replace).onPressed, isNull);
      await tester.ensureVisible(find.byType(CheckboxListTile));
      await tester.tap(find.byType(CheckboxListTile));
      await tester.pump();
      await tap(tester, "Replace this device's data");
      expect(
        tester
            .widget<TextButton>(find.widgetWithText(TextButton, 'Cancel'))
            .autofocus,
        isTrue,
      );
      await tap(tester, 'Cancel');
      expect(store.applied, 0);
      expect(store.abandoned, 1);
    },
  );

  for (final cleanupFailure in [false, true]) {
    testWidgets(
      'late cancel preserves saved outcome or actionable cleanup failure $cleanupFailure',
      (tester) async {
        final documents = ScreenDocuments()
          ..saveGate = Completer<String?>()
          ..cancelGate = Completer<void>();
        final store = ScreenStore()..artifact = artifact;
        await tester.pumpWidget(
          MaterialApp(
            home: OfflineBackupScreen(
              store: store,
              documents: documents,
              evidence: ScreenEvidence()..bytes = artifact.bytes,
              onRestored: (_) {},
            ),
          ),
        );
        await tap(tester, 'Create Backup');
        await tester.enterText(
          find.byKey(const ValueKey('backup_password')),
          fixtures.password,
        );
        await tester.enterText(
          find.byKey(const ValueKey('backup_confirmation')),
          fixtures.password,
        );
        await tester.ensureVisible(find.text('Continue'));
        await tester.tap(find.text('Continue'));
        await tester.pump();
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.inactive,
        );
        await tester.pump();
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
        await tester.pump();
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
        await tester.pump();
        expect(documents.cancellations, 0); // The SAF Activity may pause us.
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
        await tester.pump();
        await tester.ensureVisible(find.text('Cancel operation'));
        await tester.tap(find.text('Cancel operation'));
        await tester.pump();
        if (cleanupFailure) {
          documents.saveGate!.completeError(
            PlatformException(
              code: 'cleanup_incomplete',
              message: '/private/provider/secret',
            ),
          );
        } else {
          documents.saveGate!.complete('saved');
        }
        for (var n = 0; n < 100; n++) {
          await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 20)),
          );
          await tester.pump();
          if (find.text('Cancel operation').evaluate().isEmpty) break;
        }
        expect(
          find.textContaining(
            cleanupFailure
                ? 'incomplete newly created document'
                : 'Encrypted complete backup saved and authenticated',
          ),
          findsOneWidget,
        );
        documents.cancelGate!.complete();
        await tester.pumpAndSettle();
        expect(
          find.textContaining(
            cleanupFailure
                ? 'incomplete newly created document'
                : 'Encrypted complete backup saved and authenticated',
          ),
          findsOneWidget,
        );
        expect(find.textContaining('/private/provider/secret'), findsNothing);
      },
    );
  }

  testWidgets('declining recovery destination never enables replacement', (
    tester,
  ) async {
    final store = await preparedScreen(
      tester,
      ScreenDocuments()..declineSave = true,
    );
    expect(store.prepared, 0);
    expect(store.applied, 0);
    expect(find.text("Replace this device's data"), findsNothing);
  });

  testWidgets('Back awaits prepared ticket cancellation before leaving', (
    tester,
  ) async {
    final store = await preparedScreen(tester, ScreenDocuments());
    store.abandonGate = Completer<void>();
    await tester.tap(find.byType(BackButton));
    await tester.pump();
    expect(store.abandoned, 1);
    expect(store.applied, 0);
    expect(find.byType(OfflineBackupScreen), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    store.abandonGate!.complete();
    await tester.pumpAndSettle();
  });

  testWidgets(
    'backgrounding releases prepared confirmation without restoring',
    (tester) async {
      final store = await preparedScreen(tester, ScreenDocuments());
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pumpAndSettle();
      expect(store.abandoned, 1);
      expect(store.applied, 0);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(find.text("Replace this device's data"), findsNothing);
      expect(store.applied, 0);
    },
  );

  testWidgets('cancel during apply waits for restored outcome', (tester) async {
    var restored = 0;
    final store = await preparedScreen(
      tester,
      ScreenDocuments(),
      restored: (_) => restored++,
    );
    store.applyGate = Completer<RestoreResult>();
    await tester.ensureVisible(find.byType(CheckboxListTile));
    await tester.tap(find.byType(CheckboxListTile));
    await tester.pump();
    await tap(tester, "Replace this device's data");
    await tester.tap(
      find.widgetWithText(TextButton, "Replace this device's data"),
    );
    await tester.pump();
    await tester.ensureVisible(find.text('Cancel operation'));
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    await tester.pump();
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    await tester.pump();
    expect(store.requested, 0);
    expect(store.applied, 1);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    await tester.tap(find.text('Cancel operation'));
    await tester.pump();
    expect(store.requested, 1);
    expect(restored, 0);
    store.applyGate!.complete(const RestoreResult(RestoreOutcome.restored));
    await tester.pumpAndSettle();
    expect(restored, 1);
  });

  testWidgets('verified original outcome never claims successful restore', (
    tester,
  ) async {
    var restored = 0;
    final store = await preparedScreen(
      tester,
      ScreenDocuments(),
      restored: (_) => restored++,
    );
    store.outcome = RestoreOutcome.original;
    await tester.ensureVisible(find.byType(CheckboxListTile));
    await tester.tap(find.byType(CheckboxListTile));
    await tester.pump();
    await tap(tester, "Replace this device's data");
    await tap(tester, "Replace this device's data");
    expect(restored, 0);
    expect(
      find.textContaining(
        'The complete original state was verified. Nothing was replaced.',
      ),
      findsOneWidget,
    );
    expect(find.text('Create Backup'), findsOneWidget);
  });

  testWidgets(
    'unknown outcome blocks old navigation and preserves recovery guidance',
    (tester) async {
      final store = await preparedScreen(tester, ScreenDocuments());
      store.outcome = RestoreOutcome.unknown;
      await tester.ensureVisible(find.byType(CheckboxListTile));
      await tester.tap(find.byType(CheckboxListTile));
      await tester.pump();
      await tap(tester, "Replace this device's data");
      await tap(tester, "Replace this device's data");
      expect(
        find.textContaining('separate Android device or supported OS user'),
        findsOneWidget,
      );
      expect(
        find.textContaining('Do not clear data, uninstall'),
        findsOneWidget,
      );
      expect(
        tester
            .widget<PopScope>(
              find.byWidgetPredicate((widget) => widget is PopScope).first,
            )
            .canPop,
        isFalse,
      );
      expect(find.text('Create Backup'), findsNothing);
    },
  );

  for (final brightness in Brightness.values) {
    testWidgets(
      'authenticated preview and confirmation scroll at 320dp and 200% $brightness',
      (tester) async {
        tester.view.physicalSize = const Size(320, 640);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        final store = await preparedScreen(
          tester,
          ScreenDocuments(),
          brightness: brightness,
          scale: 2,
        );
        await tester.ensureVisible(find.byType(CheckboxListTile));
        await tester.tap(find.byType(CheckboxListTile));
        await tester.pump();
        await tap(tester, "Replace this device's data");
        await tap(tester, 'Cancel');
        expect(store.applied, 0);
        expect(store.abandoned, 1);
        expect(tester.takeException(), isNull);
      },
    );
    testWidgets('passphrase form scrolls at 320dp and 200% $brightness', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(320, 640);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData(brightness: brightness),
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context)
                .copyWith(textScaler: const TextScaler.linear(2)),
            child: child!,
          ),
          home: const Scaffold(body: BackupPassphraseForm()),
        ),
      );
      await tester.ensureVisible(find.text('Continue'));
      expect(tester.takeException(), isNull);
    });
  }
}
