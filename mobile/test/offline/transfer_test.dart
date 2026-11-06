import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:bhli_audit/offline/transfer.dart';

Map<String, dynamic> manifest() => {
  'format': 'bhli-audit-transfer',
  'format_version': 1,
  'package_id': '11111111-1111-4111-8111-111111111111',
  'source_installation_id': '22222222-2222-4222-8222-222222222222',
  'exported_at': '2026-11-06T01:02:03.000004Z',
  'filters': {'date_from': null, 'date_to': null, 'include_archived': true},
};
void main() {
  test(
    'rejects duplicate JSON keys before ordinary decoding can discard them',
    () {
      final bytes = encodeTransfer(manifest(), [], []);
      final d = ByteData.sublistView(bytes),
          size = d.getUint32(22, Endian.little),
          start = 30 + d.getUint16(26, Endian.little);
      final text = ascii
          .decode(bytes.sublist(start, start + size))
          .replaceFirst('audits_sha256', 'events_sha256');
      bytes.setRange(start, start + size, ascii.encode(text));
      var crc = 0xffffffff;
      for (final b in bytes.sublist(start, start + size)) {
        crc ^= b;
        for (var j = 0; j < 8; j++) {
          crc = (crc >> 1) ^ ((crc & 1) != 0 ? 0xedb88320 : 0);
        }
      }
      crc = (crc ^ 0xffffffff) & 0xffffffff;
      d.setUint32(14, crc, Endian.little);
      final central = d.getUint32(bytes.length - 6, Endian.little);
      d.setUint32(central + 16, crc, Endian.little);
      expect(() => decodeTransfer(bytes), throwsFormatException);
    },
  );
  test(
    'decodes actual Python-generated v1 package and canonical content identity',
    () {
      final result = decodeTransfer(
        File('test/fixtures/transfer/python-v1.bhlitransfer').readAsBytesSync(),
      );
      expect(
        result.audits.single['driver_name'],
        'Fictional \u99d5\u99db\u{1f69a}',
      );
      expect(result.audits.single['plate_number'], '000123');
      expect(
        result.contentSha256,
        '395fc6bde594144ac802d6e70f79664d6d7b2f0bb773bfdc216bd47cedaceb8c',
      );
    },
  );
  test(
    'retains Unicode, leading zeros, original identity and complete history',
    () {
      final a = audit(), e = create(a);
      final result = decodeTransfer(encodeTransfer(manifest(), [a], [e]));
      expect(result.audits.single, a);
      expect(result.events.single, e);
      expect(result.audits.single['plate_number'], '000123');
    },
  );
  for (final bad in [
    'origin',
    'revision',
    'archived',
    'time',
    'actor',
    'extra',
    'bool',
    'unnormalized',
    'missing',
  ]) {
    test('rejects invalid CREATE $bad', () {
      final a = audit(), e = create(a);
      if (bad == 'origin') {
        (e['after'] as Map)['profile_id'] = manifest()['package_id'];
      }
      if (bad == 'revision') a['revision'] = 2;
      if (bad == 'archived') {
        a['archived_at'] = a['created_at'];
        (e['after'] as Map)['archived_at'] = a['created_at'];
      }
      if (bad == 'time') {
        (e['after'] as Map)['updated_at'] = '2026-11-06T02:00:00.000000Z';
      }
      if (bad == 'actor') e['actor_profile_id'] = manifest()['package_id'];
      if (bad == 'extra') a['extra'] = 'x';
      if (bad == 'bool') a['revision'] = true;
      if (bad == 'unnormalized') a['driver_name'] = ' name ';
      if (bad == 'missing') a.remove('helper_name');
      expect(() => encodeTransfer(manifest(), [a], [e]), throwsFormatException);
    });
  }
  test('clock corrections preserve revision order through UPDATE and terminal ARCHIVE', () {
    final first = audit(),
        e = create(first),
        updated = {
          ...first,
          'driver_name': 'Changed',
          'revision': 2,
          'updated_at': '2026-11-05T01:02:03.000004Z',
        };
    final update = {
      ...e,
      'id': manifest()['package_id'],
      'revision': 2,
      'action': 'UPDATE',
      'created_at': updated['updated_at'],
      'before': first,
      'after': updated,
    };
    final archived = {
      ...updated,
      'revision': 3,
      'updated_at': '2026-11-06T03:00:00.000000Z',
      'archived_at': '2026-11-06T03:00:00.000000Z',
    };
    final archive = {
      ...update,
      'id': manifest()['source_installation_id'],
      'revision': 3,
      'action': 'ARCHIVE',
      'created_at': archived['updated_at'],
      'before': updated,
      'after': archived,
    };
    expect(
      decodeTransfer(
        encodeTransfer(manifest(), [archived], [e, update, archive]),
      ).audits.single['revision'],
      3,
    );
    expect(
      () => encodeTransfer(
        manifest(),
        [updated],
        [
          e,
          {
            ...update,
            'after': {...updated, 'driver_name': first['driver_name']},
          },
        ],
      ),
      throwsFormatException,
    );
    expect(
      () => encodeTransfer(
        manifest(),
        [archived],
        [
          e,
          update,
          {
            ...archive,
            'after': {...archived, 'plate_number': 'changed'},
          },
        ],
      ),
      throwsFormatException,
    );
  });
  test('rejects archive corruption and declared unsupported flags', () {
    final bytes = encodeTransfer(manifest(), [], []);
    for (final index in [6, 8, 14, 26, bytes.length - 1]) {
      final changed = Uint8List.fromList(bytes);
      changed[index] ^= 1;
      expect(() => decodeTransfer(changed), throwsFormatException);
    }
    expect(
      () => decodeTransfer(Uint8List(32 * 1024 * 1024 + 1)),
      throwsFormatException,
    );
    Object? deep = 0;
    for (var i = 0; i < 7; i++) {
      deep = [deep];
    }
    expect(() => canonicalJson(deep), throwsFormatException);
  });
  test('canonical JSON uses sorted ASCII escaped Unicode and no floats', () {
    expect(
      canonicalJson({'z': '\u{1f600}\u00e9', 'a': '\n'}),
      r'{"a":"\n","z":"\ud83d\ude00\u00e9"}',
    );
    expect(() => canonicalJson(1.5), throwsFormatException);
    expect(
      () => canonicalJson(String.fromCharCode(0xd800)),
      throwsFormatException,
    );
  });
  test('empty package has final counts and exact SHA256 identity', () {
    final bytes = encodeTransfer(manifest(), [], []);
    final result = decodeTransfer(bytes);
    expect(result.audits, isEmpty);
    expect(result.events, isEmpty);
    expect(result.manifest['record_count'], 0);
    expect(
      result.manifest['audits_sha256'],
      'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    );
    expect(result.contentSha256, matches(RegExp(r'^[0-9a-f]{64}$')));
    expect(
      () => decodeTransfer(Uint8List.fromList([...bytes, 0])),
      throwsFormatException,
    );
  });
}

Map<String, dynamic> audit() => {
  'id': '00000000-0000-4000-8000-000000000002',
  'profile_id': '00000000-0000-4000-8000-000000000001',
  'driver_name': 'Fictional \u99d5\u99db\u{1f69a}',
  'helper_name': null,
  'audit_date': '2026-11-06',
  'station': 'North',
  'plate_number': '000123',
  'remarks': 'Line\nTwo',
  'audited_by_name': 'Original Auditor',
  'created_at': '2026-11-06T01:02:03.000004Z',
  'updated_at': '2026-11-06T01:02:03.000004Z',
  'revision': 1,
  'archived_at': null,
};
Map<String, dynamic> create(Map<String, dynamic> a) => {
  'id': '00000000-0000-4000-8000-000000000003',
  'audit_id': a['id'],
  'revision': 1,
  'action': 'CREATE',
  'actor_name': a['audited_by_name'],
  'actor_profile_id': a['profile_id'],
  'created_at': a['created_at'],
  'before': null,
  'after': Map<String, dynamic>.from(a),
};
