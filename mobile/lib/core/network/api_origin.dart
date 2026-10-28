import 'dart:io';

import 'package:flutter/foundation.dart';

import 'api_failure.dart';

/// A validated origin. The transport builds endpoint paths internally.
class ApiOrigin {
  const ApiOrigin._(this.value);
  final String value;

  static ApiOrigin parse(String raw, {bool allowDebugLoopback = false}) {
    if (raw.isEmpty ||
        raw.length > 2048 ||
        RegExp(
          r'[\s\x00-\x20\x7f\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]',
        ).hasMatch(raw)) {
      throw ApiFailure.invalidOrigin;
    }
    final match = RegExp(
      r'^(https?)://(\[[0-9a-fA-F:]+\]|[a-zA-Z0-9.-]+)(?::([0-9]+))?/?$',
      caseSensitive: false,
    ).firstMatch(raw);
    if (match == null || match.end != raw.length) {
      throw ApiFailure.invalidOrigin;
    }
    final uri = Uri.tryParse(raw);
    if (uri == null || !uri.hasAuthority || uri.host.isEmpty) {
      throw ApiFailure.invalidOrigin;
    }
    final portText = match.group(3);
    final port = portText == null ? null : int.tryParse(portText);
    if (portText != null && (port == null || port < 1 || port > 65535)) {
      throw ApiFailure.invalidOrigin;
    }
    final host = uri.host.toLowerCase();
    if (host.contains(':')) {
      if (InternetAddress.tryParse(
            host.replaceAll('[', '').replaceAll(']', ''),
          ) ==
          null) {
        throw ApiFailure.invalidOrigin;
      }
    } else {
      if (host.length > 253 ||
          host
              .split('.')
              .any(
                (label) =>
                    !RegExp(r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$')
                        .hasMatch(label),
              )) {
        throw ApiFailure.invalidOrigin;
      }
      if (RegExp(r'^[0-9.]+$').hasMatch(host) &&
          (host.split('.').length != 4 ||
              host
                  .split('.')
                  .any(
                    (part) =>
                        int.tryParse(part) == null || int.parse(part) > 255,
                  ))) {
        throw ApiFailure.invalidOrigin;
      }
    }
    final scheme = uri.scheme.toLowerCase();
    if (scheme != 'https' &&
        !(kDebugMode &&
            allowDebugLoopback &&
            scheme == 'http' &&
            port != null &&
            (host == 'localhost' || host == '127.0.0.1'))) {
      throw ApiFailure.invalidOrigin;
    }
    // Retain the explicit debug port even when it is HTTP's default: a saved
    // debug origin must pass the same explicit-port validation when reloaded.
    return ApiOrigin._(
      scheme == 'http'
          ? 'http://$host:$port'
          : Uri(scheme: scheme, host: host, port: port).toString(),
    );
  }

  @override
  bool operator ==(Object other) => other is ApiOrigin && value == other.value;
  @override
  int get hashCode => value.hashCode;
  @override
  String toString() => value;
}
