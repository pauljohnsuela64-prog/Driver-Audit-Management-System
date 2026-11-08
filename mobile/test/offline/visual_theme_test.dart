import 'dart:io';
import 'dart:ui' as ui;

import 'package:bhli_audit/offline/app.dart';
import 'package:bhli_audit/offline/backup_store.dart';
import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/repository.dart';
import 'package:bhli_audit/ui/core/audit_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

class EmptyProfile implements OfflineRepository, OfflineBackupRepository {
  @override
  Future<LocalProfile?> profile() async => null;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  setUpAll(() async {
    // Optional local visual evidence uses the already installed SDK's fonts;
    // no font binaries are copied into the repo or shipped by this test.
    final fonts = Platform.environment['DAMS_PHASE6G_FONT_DIR'];
    if (fonts == null) return;
    final roboto = FontLoader('Roboto');
    for (final name in [
      'roboto-regular.ttf',
      'roboto-medium.ttf',
      'roboto-bold.ttf',
    ]) {
      roboto.addFont(
        Future.value(
          ByteData.sublistView(File('$fonts/$name').readAsBytesSync()),
        ),
      );
    }
    await roboto.load();
    final icons = FontLoader('MaterialIcons')
      ..addFont(
        Future.value(
          ByteData.sublistView(
            File('$fonts/materialicons-regular.otf').readAsBytesSync(),
          ),
        ),
      );
    await icons.load();
  });
  testWidgets(
    'offline welcome uses blue while the online theme stays unchanged',
    (tester) async {
      await tester.pumpWidget(OfflineApp(repository: EmptyProfile()));
      await tester.pumpAndSettle();
      final app = tester.widget<MaterialApp>(find.byType(MaterialApp));
      expect(app.theme!.colorScheme.primary, const Color(0xff315e8e));
      expect(app.darkTheme!.colorScheme.primary, const Color(0xffa8cff0));
      expect(
        auditTheme(Brightness.light).colorScheme.primary,
        const Color(0xff0f766e),
      );
    },
  );
  for (final spec in [
    (false, false),
    (false, true),
    (true, false),
    (true, true),
  ]) {
    final dark = spec.$1;
    final compact = spec.$2;
    testWidgets('official logo and blue welcome dark=$dark compact=$compact', (
      tester,
    ) async {
      tester.view.physicalSize = compact
          ? const Size(320, 640)
          : const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = compact ? 2 : 1;
      tester.platformDispatcher.platformBrightnessTestValue = dark
          ? Brightness.dark
          : Brightness.light;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetViewInsets);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
      const captureKey = ValueKey('visual_capture');
      await tester.pumpWidget(
        RepaintBoundary(
          key: captureKey,
          child: OfflineApp(repository: EmptyProfile()),
        ),
      );
      await tester.pumpAndSettle();
      final image = tester.widget<Image>(
        find.byWidgetPredicate(
          (w) =>
              w is Image &&
              w.semanticLabel == 'BASIC Hauling & Logistic Inc. logo',
        ),
      );
      expect(image.fit, BoxFit.contain);
      expect((image.image as AssetImage).assetName, 'assets/basic_logo.jpg');
      final directory = Platform.environment['DAMS_PHASE6G_CAPTURE_DIR'];
      Future<void> saveCapture(String suffix) async {
        if (directory == null) return;
        await tester.runAsync(() async {
          Directory(directory).createSync(recursive: true);
          final boundary = tester.renderObject<RenderRepaintBoundary>(
            find.byKey(captureKey),
          );
          final bitmap = await boundary.toImage();
          final bytes = await bitmap.toByteData(format: ui.ImageByteFormat.png);
          File(
            '$directory/welcome-${dark ? "dark" : "light"}-${compact ? "compact200" : "standard"}$suffix.png',
          ).writeAsBytesSync(bytes!.buffer.asUint8List());
          bitmap.dispose();
        });
      }

      await saveCapture('');
      if (compact) tester.view.viewInsets = const FakeViewPadding(bottom: 160);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Continue'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await saveCapture('-controls');
    });
  }
}
