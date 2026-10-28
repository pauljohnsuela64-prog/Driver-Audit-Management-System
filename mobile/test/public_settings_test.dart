import 'package:flutter_test/flutter_test.dart';
import 'package:bhli_audit/core/settings/public_settings.dart';

void main() {
  test('only public version/origin/theme round-trip', () {
    const value = PublicSettings(
      origin: 'https://fictional.invalid',
      theme: ThemeChoice.dark,
    );
    expect(PublicSettings.decode(value.encode()).origin, value.origin);
    expect(PublicSettings.decode(value.encode()).theme, ThemeChoice.dark);
    expect(value.encode(), isNot(contains('token')));
  });

  test('corrupt or expanded settings fail closed', () {
    for (final value in [
      '{}',
      '{"version":true}',
      '{"version":1,"origin":null,"theme":"system","token":"secret"}',
      'invalid',
    ]) {
      expect(() => PublicSettings.decode(value), throwsFormatException);
    }
  });

  test('fake storage failure preserves previous public settings', () async {
    final store = MemorySettingsStore();
    const before = PublicSettings(origin: 'https://fictional.invalid');
    await store.save(before);
    store.failWrites = true;
    await expectLater(
      store.save(const PublicSettings(origin: 'https://other.invalid')),
      throwsA(isA<SettingsFailure>()),
    );
    expect((await store.load()).origin, before.origin);
  });
}
