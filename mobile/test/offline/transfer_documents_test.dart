import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:bhli_audit/offline/transfer_documents.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('com.bhli.audit/transfer_documents');
  final calls = <MethodCall>[];
  setUp(() {
    calls.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call);
          if (call.method == 'createStage') {
            return '/private/generated.bhlitransfer';
          }
          if (call.method == 'pickImport') return null;
          if (call.method == 'saveStage') return true;
          return null;
        });
  });
  tearDown(
    () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null),
  );
  test('document transport passes only bounded private paths and handles picker cancellation', () async {
    final docs = TransferDocuments();
    expect(await docs.pickImport(), isNull);
    expect(calls.single.method, 'pickImport');
    expect(
      await docs.saveStage(
        '/private/generated.bhlitransfer',
        'export.bhlitransfer',
      ),
      isTrue,
    );
    final args = calls.last.arguments as Map;
    expect(args['path'], '/private/generated.bhlitransfer');
    expect(args.values.any((value) => value is Uint8List), isFalse);
  });
}
