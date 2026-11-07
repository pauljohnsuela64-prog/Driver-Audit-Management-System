import 'dart:convert';
import 'dart:isolate';
import 'dart:math';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';

const maxBackupPlaintextBytes = 64 * 1024 * 1024;
const maxBackupEnvelopeBytes = maxBackupPlaintextBytes + 112;

class BackupFailure implements Exception {
  const BackupFailure(this.code, this.message);
  final String code, message;
  @override
  String toString() => message;
}

Never _format() => throw const BackupFailure(
  'format',
  'This backup format, platform or size is not supported. Nothing was restored.',
);
void _need(bool value) {
  if (!value) _format();
}

const _unlock = BackupFailure(
  'unlock',
  'Cannot unlock this backup. Check the password or use another backup. Nothing was restored.',
);
int _platform(String value) {
  if (value == 'windows') return 1;
  if (value == 'android') return 2;
  _format();
}

Uint8List _password(String value) {
  var scalars = 0;
  for (var i = 0; i < value.length; i++) {
    final c = value.codeUnitAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      if (i + 1 >= value.length ||
          value.codeUnitAt(i + 1) < 0xdc00 ||
          value.codeUnitAt(i + 1) > 0xdfff) {
        _passwordFailure();
      }
      i++;
    } else if (c >= 0xdc00 && c <= 0xdfff) {
      _passwordFailure();
    }
    if (c < 32 || (c >= 127 && c <= 159)) _passwordFailure();
    scalars++;
  }
  if (scalars < 15 ||
      scalars > 128 ||
      value
          .replaceAll(
            RegExp(
              r'[\u0020\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]',
            ),
            '',
          )
          .isEmpty) {
    _passwordFailure();
  }
  final result = Uint8List.fromList(utf8.encode(value));
  if (result.length > 512) _passwordFailure();
  return result;
}

Never _passwordFailure() => throw const BackupFailure(
  'password',
  'Use 15–128 Unicode characters without control characters (at most 512 UTF-8 bytes).',
);
Future<SecretKey> _derive(Uint8List password, List<int> salt) async {
  final input = SecretKey(password);
  try {
    return await Argon2id(
      parallelism: 1,
      memory: 19456,
      iterations: 2,
      hashLength: 32,
    ).deriveKey(secretKey: input, nonce: salt);
  } finally {
    input.destroy();
  }
}

/// Runs the fixed-cost crypto on a worker isolate. No test RNG injection exists.
Future<Uint8List> sealBackup(
  Uint8List bytes,
  String password, {
  required String platform,
}) async {
  _need(bytes.length <= maxBackupPlaintextBytes);
  final plain = Uint8List.fromList(bytes);
  final pass = _password(password), code = _platform(platform);
  return Isolate.run(() async {
    final random = Random.secure();
    final header = Uint8List(96);
    header.setRange(0, 8, [66, 72, 76, 73, 66, 65, 75, 0]);
    final h = ByteData.sublistView(header);
    h.setUint16(8, 1, Endian.little);
    h.setUint16(10, 96, Endian.little);
    header[12] = code;
    header[13] = 1;
    header[14] = 1;
    h.setUint32(16, 2, Endian.little);
    h.setUint32(20, 19456, Endian.little);
    h.setUint32(24, 2, Endian.little);
    h.setUint32(28, 1, Endian.little);
    for (var i = 32; i < 60; i++) {
      header[i] = random.nextInt(256);
    }
    h.setUint64(60, plain.length, Endian.little);
    h.setUint64(68, plain.length + 16, Endian.little);
    h.setUint32(76, 1, Endian.little);
    SecretKey? key;
    try {
      key = await _derive(pass, header.sublist(32, 48));
      final box = await AesGcm.with256bits().encrypt(
        plain,
        secretKey: key,
        nonce: header.sublist(48, 60),
        aad: header,
      );
      return Uint8List.fromList([
        ...header,
        ...box.cipherText,
        ...box.mac.bytes,
      ]);
    } finally {
      key?.destroy();
      pass.fillRange(0, pass.length, 0);
      plain.fillRange(0, plain.length, 0);
    }
  });
}

/// Structural validation precedes KDF; plaintext is returned only after AEAD.
Future<Uint8List> openBackup(
  Uint8List bytes,
  String password, {
  required String platform,
}) async {
  _need(bytes.length >= 112 && bytes.length <= maxBackupEnvelopeBytes);
  final data = Uint8List.fromList(bytes), code = _platform(platform);
  final h = ByteData.sublistView(data);
  _need(
    data.sublist(0, 8).join(',') == '66,72,76,73,66,65,75,0' &&
        h.getUint16(8, Endian.little) == 1 &&
        h.getUint16(10, Endian.little) == 96 &&
        data[12] == code &&
        data[13] == 1 &&
        data[14] == 1 &&
        data[15] == 0 &&
        h.getUint32(16, Endian.little) == 2 &&
        h.getUint32(20, Endian.little) == 19456 &&
        h.getUint32(24, Endian.little) == 2 &&
        h.getUint32(28, Endian.little) == 1 &&
        h.getUint32(76, Endian.little) == 1 &&
        data.sublist(80, 96).every((b) => b == 0),
  );
  // Compare the high halves separately before reading a possibly signed uint64.
  _need(
    h.getUint32(64, Endian.little) == 0 && h.getUint32(72, Endian.little) == 0,
  );
  final length = h.getUint32(60, Endian.little);
  _need(
    length <= maxBackupPlaintextBytes &&
        h.getUint32(68, Endian.little) == length + 16 &&
        data.length == length + 112,
  );
  final pass = _password(password);
  return Isolate.run(() async {
    SecretKey? key;
    try {
      key = await _derive(pass, data.sublist(32, 48));
      final result = await AesGcm.with256bits().decrypt(
        SecretBox(
          data.sublist(96, data.length - 16),
          nonce: data.sublist(48, 60),
          mac: Mac(data.sublist(data.length - 16)),
        ),
        secretKey: key,
        aad: data.sublist(0, 96),
      );
      return Uint8List.fromList(result);
    } on SecretBoxAuthenticationError {
      throw _unlock;
    } finally {
      key?.destroy();
      pass.fillRange(0, pass.length, 0);
    }
  });
}
