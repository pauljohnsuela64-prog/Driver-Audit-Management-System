import 'dart:typed_data';
import 'dart:convert';
import 'dart:io';

import 'package:cryptography/cryptography.dart';

import 'package:flutter_test/flutter_test.dart';
import 'package:bhli_audit/offline/backup_crypto.dart';

void main() {
  test('opens authenticated Python Android golden and writes reciprocal Dart fixture', () async {
    final manifest = jsonDecode(
      File('test/fixtures/backup/python-fixture.json').readAsStringSync(),
    ) as Map;
    final plain = File('test/fixtures/backup/python-android-state.ndjson')
        .readAsBytesSync();
    final encrypted = File('test/fixtures/backup/python-android.bhlibackup')
        .readAsBytesSync();
    expect(
      await openBackup(
        encrypted,
        manifest['password'] as String,
        platform: 'android',
      ),
      plain,
    );
    final dart = await sealBackup(
      plain,
      manifest['password'] as String,
      platform: 'android',
    );
    expect(
      await openBackup(
        dart,
        manifest['password'] as String,
        platform: 'android',
      ),
      plain,
    );
    // Only explicit fixture-generation invocations write this test-owned artifact.
    if (Platform.environment['BHLI_WRITE_BACKUP_FIXTURE'] == '1') {
      File('test/fixtures/backup/dart-android.bhlibackup')
          .writeAsBytesSync(dart);
    }
  });
  test('pinned Argon2id implements RFC9106 section 5.3 vector', () async {
    final key =
        await Argon2id(
          parallelism: 4,
          memory: 32,
          iterations: 3,
          hashLength: 32,
        ).deriveKey(
          secretKey: SecretKey(List.filled(32, 1)),
          nonce: List.filled(16, 2),
          optionalSecret: List.filled(8, 3),
          associatedData: List.filled(12, 4),
        );
    expect(
      (await key.extractBytes())
          .map((v) => v.toRadixString(16).padLeft(2, '0'))
          .join(),
      '0d640df58d78766c08c037a34a8b53c9d01ef0452d75b65eb52520e96b01e659',
    );
  });
  test('pinned AES256 GCM implements NIST zero-key block vector', () async {
    final box = await AesGcm.with256bits().encrypt(
      List.filled(16, 0),
      secretKey: SecretKey(List.filled(32, 0)),
      nonce: List.filled(12, 0),
    );
    String hex(List<int> v) =>
        v.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    expect(hex(box.cipherText), 'cea7403d4d606b6e074ec5d3baf39d18');
    expect(hex(box.mac.bytes), 'd0d1c8a799996bf0265b98b5d48ab919');
  });

  const password = 'fictional long passphrase';
  test(
    'encrypts fresh authenticated envelope and roundtrips exact plaintext',
    () async {
      final plain = Uint8List.fromList([0, 1, 2, 255]);
      final a = await sealBackup(plain, password, platform: 'android');
      final b = await sealBackup(plain, password, platform: 'android');
      expect(a.length, 116);
      expect(a.sublist(0, 8), [66, 72, 76, 73, 66, 65, 75, 0]);
      expect(a.sublist(32, 60), isNot(b.sublist(32, 60)));
      expect(await openBackup(a, password, platform: 'android'), plain);
    },
  );
  test(
    'wrong password and tag failure share safe failure without plaintext',
    () async {
      final a = await sealBackup(
        Uint8List.fromList([42]),
        password,
        platform: 'android',
      );
      final tampered = Uint8List.fromList(a);
      tampered.last ^= 1;
      for (final attempt in [
        () => openBackup(
          a,
          'another long fictional password',
          platform: 'android',
        ),
        () => openBackup(tampered, password, platform: 'android'),
      ]) {
        await expectLater(
          attempt(),
          throwsA(isA<BackupFailure>().having((e) => e.code, 'code', 'unlock')),
        );
      }
    },
  );
  test(
    'authenticates salt, nonce and ciphertext before exposing bytes',
    () async {
      final sealed = await sealBackup(
        Uint8List.fromList([42]),
        password,
        platform: 'android',
      );
      for (final offset in [32, 48, 96]) {
        final modified = Uint8List.fromList(sealed);
        modified[offset] ^= 1;
        await expectLater(
          openBackup(modified, password, platform: 'android'),
          throwsA(isA<BackupFailure>().having((e) => e.code, 'code', 'unlock')),
        );
      }
    },
  );
  test(
    'password bytes retain whitespace and Unicode spelling exactly',
    () async {
      const exact = '  fictional \u00e9 passphrase  ';
      final sealed = await sealBackup(
        Uint8List.fromList([42]),
        exact,
        platform: 'android',
      );
      expect(await openBackup(sealed, exact, platform: 'android'), [42]);
      for (final altered in [
        exact.trim(),
        exact.replaceAll('\u00e9', 'e\u0301'),
      ]) {
        await expectLater(
          openBackup(sealed, altered, platform: 'android'),
          throwsA(isA<BackupFailure>().having((e) => e.code, 'code', 'unlock')),
        );
      }
    },
  );
  test('rejects policy violations and hostile framing', () async {
    for (final value in [
      'short',
      ' ' * 15,
      '\u2003' * 15,
      '12345678901234\n',
      'x' * 129,
      String.fromCharCode(0xd800) + 'x' * 15,
    ]) {
      await expectLater(
        sealBackup(Uint8List(0), value, platform: 'android'),
        throwsA(isA<BackupFailure>()),
      );
    }
    final a = await sealBackup(Uint8List(0), password, platform: 'android');
    final bad = Uint8List.fromList(a);
    bad[21] = 0;
    await expectLater(
      openBackup(bad, password, platform: 'android'),
      throwsA(isA<BackupFailure>().having((e) => e.code, 'code', 'format')),
    );
    await expectLater(
      openBackup(Uint8List.fromList([...a, 0]), password, platform: 'android'),
      throwsA(isA<BackupFailure>()),
    );
    await expectLater(
      openBackup(a, password, platform: 'windows'),
      throwsA(isA<BackupFailure>()),
    );
  });
}
