import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:bhli_audit/offline/store_lease.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('com.bhli.audit/offline_store');
  test(
    'native token retained until checked release, failed release remains held',
    () async {
      final calls = <MethodCall>[];
      var failRelease = true;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            calls.add(call);
            if (call.method == 'acquire') return 'native-opaque-token';
            if (call.method == 'release' && failRelease) {
              throw PlatformException(code: 'storage');
            }
            return null;
          });
      final lease = await OfflineStoreLease.acquire();
      await lease.ensureHeld();
      await expectLater(lease.release(), throwsA(isA<PlatformException>()));
      await lease.ensureHeld();
      failRelease = false;
      await lease.release();
      await expectLater(lease.ensureHeld(), throwsStateError);
      expect(calls.map((c) => c.method), [
        'acquire',
        'ensureHeld',
        'release',
        'ensureHeld',
        'release',
      ]);
      expect(
        calls
            .skip(1)
            .every(
              (c) => (c.arguments as Map)['token'] == 'native-opaque-token',
            ),
        isTrue,
      );
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null);
    },
  );
}
