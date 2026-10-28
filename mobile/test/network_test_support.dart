import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

const tokenA = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';
const tokenB = 'BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB';

Map<String, Object?> auditJson({int id = 1}) => {
  'id': id,
  'version': 3,
  'driver_name': 'José 🚚',
  'helper_name': null,
  'audit_date': '2024-02-29',
  'station': 'Fictional North',
  'plate_number': '000123',
  'remarks': '<b>plain text</b>\nSecond line',
  'audited_by_name': 'Original Snapshot',
  'audited_by_user_id': 8,
  'updated_by_user_id': null,
  'deleted_by_user_id': null,
  'deleted_at': null,
  'created_at': '2026-10-28T08:00:00Z',
  'updated_at': '2026-10-28T16:30:00+08:00',
};

Map<String, Object?> userJson({String role = 'AUDITOR'}) => {
  'id': 8,
  'username': 'fictional',
  'full_name': 'Current Account Name',
  'role': role,
};

Map<String, Object?> leaseJson({String token = tokenA}) => {
  'access_token': token,
  'token_type': 'bearer',
  'expires_at': '2026-10-28T20:00:00Z',
};

http.StreamedResponse jsonResponse(
  Object? data, {
  int status = 200,
  Map<String, String> headers = const {},
}) => http.StreamedResponse(
  Stream.value(utf8.encode(jsonEncode(data))),
  status,
  headers: {'content-type': 'application/json', ...headers},
);

class RecordingClient extends http.BaseClient {
  RecordingClient(this.handler, {this.onClose});
  final FutureOr<http.StreamedResponse> Function(http.BaseRequest) handler;
  final void Function()? onClose;
  final requests = <http.BaseRequest>[];
  bool closed = false;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requests.add(request);
    return handler(request);
  }

  @override
  void close() {
    closed = true;
    onClose?.call();
  }
}
