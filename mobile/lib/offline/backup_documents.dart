import 'package:flutter/services.dart';

abstract interface class BackupDocuments {
  Future<String?> pickBackup();
  Future<String?> saveBackup(String handle, String name);
  Future<void> cancel();
}

/// The Android picker returns only private encrypted evidence handles.
class NativeBackupDocuments implements BackupDocuments {
  static const _channel = MethodChannel('com.bhli.audit/backup_documents');
  @override
  Future<String?> pickBackup() => _channel.invokeMethod<String>('pickBackup');
  @override
  Future<String?> saveBackup(String handle, String name) => _channel
      .invokeMethod<String>('saveBackup', {'handle': handle, 'name': name});
  @override
  Future<void> cancel() => _channel.invokeMethod<void>('cancel');
}
