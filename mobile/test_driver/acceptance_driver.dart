import 'dart:io';

import 'package:integration_test/integration_test_driver_extended.dart';

Future<void> main() => integrationDriver(
  onScreenshot: (name, image, [args]) async {
    final phase4b = RegExp(r'^phase4b-[a-z0-9-]+$').hasMatch(name);
    if (!phase4b &&
        !RegExp(r'^demo_(admin|auditor)-(audits|details|signed-out)$')
            .hasMatch(name)) {
      return false;
    }
    final directory = Directory(
      phase4b ? '../artifacts/phase4b-android' : '../artifacts/phase4a-android',
    );
    await directory.create(recursive: true);
    await File('${directory.path}/$name.png').writeAsBytes(image, flush: true);
    return image.isNotEmpty;
  },
);
