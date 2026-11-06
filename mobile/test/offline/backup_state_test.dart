import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:bhli_audit/offline/backup_state.dart';

Map<String, List<Map<String, Object?>>> emptyRows() => {
  'app_meta': [
    {'key': 'app_id', 'value': 'com.bhli.audit.offline'},
    {'key': 'installation_id', 'value': '11111111-1111-4111-8111-111111111111'},
  ],
  'local_profile': [],
  'auditor_identities': [],
  'audit_records': [],
  'audit_events': [],
  'transfer_receipts': [],
};
Uint8List encode(
  Map<String, List<Map<String, Object?>>> rows, {
  int? sequence,
}) => encodeBackupState(
  rows,
  platform: 'android',
  backupId: '22222222-2222-4222-8222-222222222222',
  createdAt: '2026-11-06T01:02:03.000004Z',
  sourceVersion: '1.0.0+2',
  sequence: sequence,
);
void main() {
  test('returned metadata counts cannot mutate authenticated state', () {
    final state = decodeBackupState(encode(emptyRows()), platform: 'android');
    expect(
      () => (state.metadata['counts'] as Map)['app_meta'] = 1,
      throwsUnsupportedError,
    );
  });

  test('matches Python full-state golden with raw archive history and sequence gaps', () {
    final bytes = File('test/fixtures/backup/python-android-state.ndjson')
        .readAsBytesSync();
    final state = decodeBackupState(bytes, platform: 'android');
    expect(
      state.digest,
      '143427275430e2fd11ef5fa3f395bf9f1ef9d597afba7fcf989ba899bf5fa08d',
    );
    expect(state.sequence, 90);
    expect(state.rows['audit_events']!.length, 3);
    expect(state.rows['auditor_identities']!.length, 2);
    expect(state.rows['transfer_receipts']!.length, 1);
    expect(
      encodeBackupState(
        state.rows,
        platform: 'android',
        sequence: state.sequence,
        backupId: state.metadata['backup_id'] as String,
        createdAt: state.metadata['created_at'] as String,
        sourceVersion: state.metadata['source_version'] as String,
      ),
      bytes,
    );
    expect(
      () => state.rows['audit_records']!.single['seq'] = 1,
      throwsUnsupportedError,
    );
  });
  test('rejects complete-history, identity and raw JSON violations', () {
    final original = decodeBackupState(
      File('test/fixtures/backup/python-android-state.ndjson')
          .readAsBytesSync(),
      platform: 'android',
    );
    Map<String, List<Map<String, Object?>>> copy() => {
      for (final e in original.rows.entries)
        e.key: e.value.map((r) => Map<String, Object?>.from(r)).toList(),
    };
    final mutations = <void Function(Map<String, List<Map<String, Object?>>>)>[
      (r) => r['audit_events']!.removeLast(),
      (r) => r['auditor_identities']!.clear(),
      (r) => r['audit_events']!.last['id'] = r['audit_events']!.first['id'],
      (r) => r['audit_records']!.single['revision'] = '3',
      (r) => r['transfer_receipts']!.single['imported_count'] = '1',
      (r) => r['audit_events']!.first['after_json'] =
          (r['audit_events']!.first['after_json'] as String).replaceFirst(
            '{',
            '{"id":"duplicate",',
          ),
      (r) => r['audit_events']!.first['after_json'] = "${'[' * 8}0${']' * 8}",
    ];
    for (final mutate in mutations) {
      final rows = copy();
      mutate(rows);
      expect(() => encode(rows, sequence: 90), throwsFormatException);
    }
    expect(() => encode(original.rows, sequence: 0), throwsFormatException);
  });
  test('preserves noncanonical raw history and legacy offset timestamps', () {
    final original = decodeBackupState(
      File('test/fixtures/backup/python-android-state.ndjson')
          .readAsBytesSync(),
      platform: 'android',
    );
    final rows = {
      for (final e in original.rows.entries)
        e.key: e.value.map((r) => Map<String, Object?>.from(r)).toList(),
    };
    for (final event in rows['audit_events']!) {
      for (final key in ['before_json', 'after_json']) {
        if (event[key] is String) {
          event[key] =
              "  ${(event[key] as String).replaceAll('Z"', '+00:00"')}  ";
        }
      }
    }
    final state = decodeBackupState(
      encode(rows, sequence: 90),
      platform: 'android',
    );
    expect(state.rows, rows);
  });
  test('preserves SQLite maximum integer watermark and rejects ID ceiling', () {
    expect(
      decodeBackupState(
        encode(emptyRows(), sequence: 9223372036854775807),
        platform: 'android',
      ).sequence,
      9223372036854775807,
    );
    final rows = emptyRows();
    rows['auditor_identities'] = List.generate(
      40002,
      (_) => {'id': '11111111-1111-4111-8111-111111111111'},
    );
    expect(() => encode(rows), throwsFormatException);
  });

  test('empty full state preserves absent sequence and binds its digest', () {
    final bytes = encode(emptyRows());
    final state = decodeBackupState(bytes, platform: 'android');
    expect(state.rows, emptyRows());
    expect(state.sequence, isNull);
    expect(state.digest, matches(RegExp(r'^[a-f0-9]{64}$')));
    expect(
      ascii.decode(bytes),
      contains('"sqlite_sequence_audit_records":null'),
    );
    expect(encode(state.rows), bytes);
  });
  test('digest includes sequence, excludes generation metadata', () {
    final a = decodeBackupState(encode(emptyRows()), platform: 'android');
    final b = decodeBackupState(
      encode(emptyRows(), sequence: 99),
      platform: 'android',
    );
    expect(a.digest, isNot(b.digest));
  });
  test('rejects unknown row columns and missing metadata rows', () {
    final rows = emptyRows();
    rows['app_meta']![0]['extra'] = 1;
    expect(() => encode(rows), throwsFormatException);
    final missing = emptyRows();
    missing['app_meta']!.removeLast();
    expect(() => encode(missing), throwsFormatException);
  });
  test(
    'rejects duplicate keys, foreign platform, noncanonical and trailing bytes',
    () {
      final bytes = encode(emptyRows());
      for (final value in [
        ascii
            .decode(bytes)
            .replaceFirst(
              '"kind":"metadata"',
              '"kind":"metadata","kind":"metadata"',
            ),
        '${ascii.decode(bytes)}\n',
      ]) {
        expect(
          () => decodeBackupState(
            Uint8List.fromList(utf8.encode(value)),
            platform: 'android',
          ),
          throwsFormatException,
        );
      }
      expect(
        () => decodeBackupState(bytes, platform: 'windows'),
        throwsFormatException,
      );
    },
  );
}
