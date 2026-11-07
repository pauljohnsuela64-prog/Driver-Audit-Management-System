import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';

import 'backup_crypto.dart';
import 'backup_store.dart';

/// Native grants only generated encrypted evidence and one fixed bounded marker.
class NativeBackupEvidence implements BackupEvidence {
  static const _channel = MethodChannel('com.bhli.audit/backup_evidence');
  Future<Uint8List> _readBounded(String path) async {
    final file = File(path);
    if (await file.length() > maxBackupEnvelopeBytes) {
      throw const FormatException('Backup exceeds supported size.');
    }
    final builder = BytesBuilder(copy: false);
    await for (final chunk in file.openRead()) {
      if (builder.length + chunk.length > maxBackupEnvelopeBytes) {
        throw const FormatException('Backup exceeds supported size.');
      }
      builder.add(chunk);
    }
    return builder.takeBytes();
  }

  @override
  Future<String> retain(Uint8List envelope) async {
    if (envelope.length > maxBackupEnvelopeBytes) {
      throw const FormatException('Backup exceeds supported size.');
    }
    final created = await _channel.invokeMapMethod<String, String>(
      'createEvidence',
    );
    if (created == null ||
        created['handle'] == null ||
        created['path'] == null) {
      throw const FileSystemException(
        'Private encrypted evidence unavailable.',
      );
    }
    await File(created['path']!).writeAsBytes(envelope, flush: true);
    await _channel.invokeMethod<void>('syncEvidence', {
      'handle': created['handle'],
    });
    return created['handle']!;
  }

  @override
  Future<Uint8List> read(String handle) async {
    final path = await _channel.invokeMethod<String>('readEvidencePath', {
      'handle': handle,
    });
    if (path == null) {
      throw const FileSystemException(
        'Private encrypted evidence unavailable.',
      );
    }
    return _readBounded(path);
  }

  @override
  Future<Uint8List?> readMarker() =>
      _channel.invokeMethod<Uint8List>('readMarker');
  @override
  Future<void> writeMarker(Uint8List bytes) {
    if (bytes.isEmpty || bytes.length > 4096) {
      throw const FormatException('Recovery marker exceeds supported size.');
    }
    return _channel.invokeMethod<void>('writeMarker', {'bytes': bytes});
  }

  @override
  Future<void> clearMarker() => _channel.invokeMethod<void>('clearMarker');
}
