import 'dart:async';

import 'package:bhli_audit/main_offline.dart';
import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/repository.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class PendingRepository implements OfflineRepository {
  bool closed = false;
  @override
  Future<void> close() async => closed = true;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  testWidgets(
    'storage failure remains scrollable in compact large-text landscape',
    (tester) async {
      tester.view.physicalSize = const Size(640, 320);
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await tester.pumpWidget(
        OfflineBootstrap(
          openRepository: () async {
            throw const OfflineFailure('storage', 'private details');
          },
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.ensureVisible(find.text('Retry'));
      expect(find.text('Retry'), findsOneWidget);
    },
  );
  testWidgets(
    'failed initialization exposes only a useful safe error and permits retry',
    (tester) async {
      var attempts = 0;
      await tester.pumpWidget(
        OfflineBootstrap(
          openRepository: () async {
            attempts++;
            throw StateError('private database path and SQL details');
          },
        ),
      );
      await tester.pumpAndSettle();
      expect(find.textContaining('private database'), findsNothing);
      expect(find.textContaining('Local storage'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(attempts, 2);
    },
  );

  testWidgets(
    'a late database opened after disposal is closed rather than leaked',
    (tester) async {
      final ready = Completer<OfflineRepository>();
      final repository = PendingRepository();
      await tester.pumpWidget(
        OfflineBootstrap(openRepository: () => ready.future),
      );
      await tester.pumpWidget(const SizedBox.shrink());
      ready.complete(repository);
      await tester.pump();
      await tester.pump();
      expect(repository.closed, true);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'unsupported schema is not described as a resettable empty installation',
    (tester) async {
      await tester.pumpWidget(
        OfflineBootstrap(
          openRepository: () async {
            throw const OfflineFailure(
              'schema',
              'This local database is not supported by this app.',
            );
          },
        ),
      );
      await tester.pumpAndSettle();
      expect(find.textContaining('not supported'), findsOneWidget);
      expect(find.textContaining('Reset'), findsNothing);
    },
  );
}
