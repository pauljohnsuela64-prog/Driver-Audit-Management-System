import 'package:flutter_test/flutter_test.dart';
import 'package:bhli_audit/app/privacy_policy.dart';

void main() {
  test('release capture is always denied', () {
    expect(
      allowFictionalCapture(
        debugBuild: false,
        requested: true,
        origin: 'http://127.0.0.1:8765',
      ),
      isFalse,
    );
  });
  test(
    'capture needs an explicit debug fixture and explicit loopback port',
    () {
      expect(
        allowFictionalCapture(
          debugBuild: true,
          requested: true,
          origin: 'http://127.0.0.1:8765',
        ),
        isTrue,
      );
      for (final origin in [
        null,
        'https://service.invalid',
        'http://10.0.2.2:8765',
        'http://localhost',
        'http://user@localhost:8765',
        'http://localhost:8765/other',
      ]) {
        expect(
          allowFictionalCapture(
            debugBuild: true,
            requested: true,
            origin: origin,
          ),
          isFalse,
        );
      }
      expect(
        allowFictionalCapture(
          debugBuild: true,
          requested: false,
          origin: 'http://127.0.0.1:8765',
        ),
        isFalse,
      );
    },
  );
}
