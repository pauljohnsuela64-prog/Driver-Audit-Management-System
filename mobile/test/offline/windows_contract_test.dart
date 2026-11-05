import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import '../../lib/offline/models.dart';

void main() {
  final contract = jsonDecode(
    File('test/fixtures/offline_contract.json').readAsStringSync(),
  ) as Map<String, dynamic>;
  for (final value in contract['vectors'] as List<dynamic>) {
    final vector = value as Map<String, dynamic>;
    test('Windows shared contract: ${vector['name']}', () {
      final input = Map<String, Object?>.from(vector['input'] as Map);
      if (vector.containsKey('error')) {
        expect(
          () => AuditValues.fromJson(input),
          throwsA(
            isA<OfflineFailure>().having((e) => e.code, 'code', 'validation'),
          ),
        );
      } else {
        expect(AuditValues.fromJson(input).toJson(), vector['expected']);
      }
    });
  }
  for (final entry
      in (contract['codepoint_limits'] as Map<String, dynamic>).entries) {
    test('Windows shared codepoint boundary: ${entry.key}', () {
      final input = <String, Object?>{
        'driver_name': 'Driver',
        'audit_date': '2024-02-29',
        'station': 'Station',
        'plate_number': 'TEST',
      };
      input[entry.key] = List.filled(entry.value as int, '😀').join();
      expect(AuditValues.fromJson(input).toJson()[entry.key], input[entry.key]);
      input[entry.key] = '${input[entry.key]}😀';
      expect(() => AuditValues.fromJson(input), throwsA(isA<OfflineFailure>()));
    });
  }
}
