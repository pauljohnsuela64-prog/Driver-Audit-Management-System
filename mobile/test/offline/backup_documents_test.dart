import 'package:bhli_audit/offline/backup_documents.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('com.bhli.audit/backup_documents');
  final calls = <MethodCall>[];
  setUp(() {
    calls.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call);
          return call.method == 'cancel' ? null : 'retained.bhlibackup';
        });
  });
  tearDown(
    () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null),
  );
  test(
    'native documents exchange opaque handles without arbitrary paths',
    () async {
      final documents = NativeBackupDocuments();
      expect(await documents.pickBackup(), 'retained.bhlibackup');
      expect(
        await documents.saveBackup('source.bhlibackup', 'backup.bhlibackup'),
        'retained.bhlibackup',
      );
      await documents.cancel();
      expect(calls.map((call) => call.method), [
        'pickBackup',
        'saveBackup',
        'cancel',
      ]);
      expect(calls[1].arguments, {
        'handle': 'source.bhlibackup',
        'name': 'backup.bhlibackup',
      });
    },
  );
  test('picker cancellation returns null', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (_) async => null);
    expect(await NativeBackupDocuments().pickBackup(), isNull);
  });
}
