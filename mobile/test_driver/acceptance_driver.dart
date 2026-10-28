import 'dart:io';

import 'package:integration_test/integration_test_driver_extended.dart';

Future<void> main() => integrationDriver(
  onScreenshot: (name, image, [args]) async {
    if (!RegExp(r'^demo_(admin|auditor)-(audits|details|signed-out)$')
        .hasMatch(name)) {
      return false;
    }
    final directory = Directory('../artifacts/phase4a-android');
    await directory.create(recursive: true);
    await File('${directory.path}/$name.png').writeAsBytes(image, flush: true);
    return image.isNotEmpty;
  },
);
