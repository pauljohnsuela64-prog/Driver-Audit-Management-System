import 'package:flutter/services.dart';

/// Proof used by the queued owner. Fixtures may provide it only with an injected
/// SQLite factory; production always acquires the native default-store lease.
abstract interface class StoreOwnership {
  Future<void> ensureHeld();
  Future<void> release();
}

class OfflineStoreLease implements StoreOwnership {
  OfflineStoreLease._(this._token);
  static const _channel = MethodChannel('com.bhli.audit/offline_store');
  final String _token;
  bool _released = false;
  static Future<OfflineStoreLease> acquire() async {
    final token = await _channel.invokeMethod<String>('acquire');
    if (token == null || token.isEmpty) {
      throw StateError('Native storage ownership unavailable.');
    }
    return OfflineStoreLease._(token);
  }

  @override
  Future<void> ensureHeld() async {
    if (_released) throw StateError('Storage ownership has been released.');
    await _channel.invokeMethod<void>('ensureHeld', {'token': _token});
  }

  @override
  Future<void> release() async {
    if (_released) return;
    await _channel.invokeMethod<void>('release', {'token': _token});
    _released = true;
  }
}
