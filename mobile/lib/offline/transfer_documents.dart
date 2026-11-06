import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';

/// Native SAF transport exchanges generated private paths, never package bytes.
class TransferDocuments {
  static const _channel = MethodChannel('com.bhli.audit/transfer_documents');
  static const maxBytes = 32 * 1024 * 1024;
  Future<String?> pickImport() => _channel.invokeMethod<String>('pickImport');
  Future<String> stage(Uint8List bytes) async {
    if (bytes.length > maxBytes) {
      throw const FormatException('Narrow the date range and try again.');
    }
    final path = await _channel.invokeMethod<String>('createStage');
    if (path == null) {
      throw const FileSystemException('Private staging unavailable');
    }
    try {
      await File(path).writeAsBytes(bytes, flush: true);
      return path;
    } catch (_) {
      await deleteStage(path);
      rethrow;
    }
  }

  Future<Uint8List> readStage(String path) async {
    final file = File(path);
    if (await file.length() > maxBytes) {
      throw const FormatException('Narrow the date range and try again.');
    }
    final data = BytesBuilder(copy: false);
    await for (final chunk in file.openRead()) {
      if (data.length + chunk.length > maxBytes) {
        throw const FormatException('Transfer exceeds safe limits.');
      }
      data.add(chunk);
    }
    return data.takeBytes();
  }

  Future<bool> saveStage(String path, String name) async =>
      await _channel.invokeMethod<bool>('saveStage', {
        'path': path,
        'name': name,
      }) ??
      false;
  Future<void> deleteStage(String path) =>
      _channel.invokeMethod<void>('deleteStage', {'path': path});
  Future<void> cancel() => _channel.invokeMethod<void>('cancel');
}
