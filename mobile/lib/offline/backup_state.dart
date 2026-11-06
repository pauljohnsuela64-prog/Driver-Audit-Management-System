import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

import 'models.dart';

const _max = 64 * 1024 * 1024;
Never _bad() => throw const FormatException(
  'Invalid or unsupported complete backup state. Nothing was restored.',
);
void _need(bool value) {
  if (!value) _bad();
}

class BackupState {
  BackupState({
    required Map<String, List<Map<String, Object?>>> rows,
    required Map<String, Object?> metadata,
    required this.sequence,
    required this.platform,
    required this.digest,
  }) : rows = Map.unmodifiable({
         for (final e in rows.entries)
           e.key: List<Map<String, Object?>>.unmodifiable(
             e.value.map((r) => Map<String, Object?>.unmodifiable(r)),
           ),
       }),
       metadata = Map.unmodifiable({
         ...metadata,
         if (metadata['counts'] is Map)
           'counts': Map.unmodifiable(metadata['counts'] as Map),
       });
  final Map<String, List<Map<String, Object?>>> rows;
  final Map<String, Object?> metadata;
  final int? sequence;
  final String platform, digest;
}

String _canonical(Object? value) {
  String emit(Object? v, int depth) {
    if (depth > 6) _bad();
    if (v == null) return 'null';
    if (v is int) {
      _need(v >= 0 && v <= 9223372036854775807);
      return '$v';
    }
    if (v is String) {
      final b = StringBuffer('"');
      for (var i = 0; i < v.length; i++) {
        final c = v.codeUnitAt(i);
        if (c >= 0xd800 && c <= 0xdbff) {
          _need(
            i + 1 < v.length &&
                v.codeUnitAt(i + 1) >= 0xdc00 &&
                v.codeUnitAt(i + 1) <= 0xdfff,
          );
        } else if (c >= 0xdc00 && c <= 0xdfff) {
          _need(
            i > 0 &&
                v.codeUnitAt(i - 1) >= 0xd800 &&
                v.codeUnitAt(i - 1) <= 0xdbff,
          );
        }
        const escapes = {
          8: r'\b',
          9: r'\t',
          10: r'\n',
          12: r'\f',
          13: r'\r',
          34: r'\"',
          92: r'\\',
        };
        if (escapes.containsKey(c)) {
          b.write(escapes[c]);
        } else if (c < 32 || c > 126) {
          b.write('\\u${c.toRadixString(16).padLeft(4, '0')}');
        } else {
          b.writeCharCode(c);
        }
      }
      return '${b.toString()}"';
    }
    if (v is List) return '[${v.map((e) => emit(e, depth + 1)).join(',')}]';
    if (v is Map) {
      _need(
        v.keys.every((k) => k is String && k.codeUnits.every((c) => c < 128)),
      );
      final keys = v.keys.cast<String>().toList()..sort();
      return '{${keys.map((k) => '${emit(k, depth + 1)}:${emit(v[k], depth + 1)}').join(',')}}';
    }
    _bad();
  }

  return emit(value, 0);
}

class _Json {
  _Json(this.s);
  final String s;
  int p = 0;
  void ws() {
    while (p < s.length && [9, 10, 13, 32].contains(s.codeUnitAt(p))) {
      p++;
    }
  }

  Object? value([int depth = 0]) {
    ws();
    _need(depth <= 6 && p < s.length);
    final c = s[p];
    if (c == '"') {
      final start = p++;
      while (p < s.length) {
        final c = s[p++];
        if (c == '\\') {
          _need(p < s.length);
          p++;
        } else if (c == '"') {
          final v = jsonDecode(s.substring(start, p));
          _canonical(v);
          return v;
        }
      }
      _bad();
    }
    if (c == '{' || c == '[') {
      p++;
      final object = c == '{';
      final map = <String, dynamic>{};
      final list = <dynamic>[];
      ws();
      if (p < s.length && s[p] == (object ? '}' : ']')) {
        p++;
        return object ? map : list;
      }
      while (true) {
        if (object) {
          final key = value(depth + 1);
          _need(key is String && !map.containsKey(key));
          ws();
          _need(p < s.length && s[p++] == ':');
          map[key as String] = value(depth + 1);
        } else {
          list.add(value(depth + 1));
        }
        ws();
        _need(p < s.length);
        final end = s[p++];
        if (end == (object ? '}' : ']')) return object ? map : list;
        _need(end == ',');
      }
    }
    for (final word in ['null', 'true', 'false']) {
      if (s.startsWith(word, p)) {
        p += word.length;
        return word == 'null' ? null : word == 'true';
      }
    }
    final start = p;
    while (p < s.length && s.codeUnitAt(p) >= 48 && s.codeUnitAt(p) <= 57) {
      p++;
    }
    _need(p > start);
    final token = s.substring(start, p);
    _need(token == '0' || !token.startsWith('0'));
    final n = int.tryParse(token);
    _need(n != null && n <= 9223372036854775807);
    return n;
  }
}

Object? _inner(String text) {
  _need(utf8.encode(text).length <= 1024 * 1024);
  final parser = _Json(text);
  final value = parser.value();
  parser.ws();
  _need(parser.p == text.length);
  return value;
}

bool _same(Object? a, Object? b) {
  if (a is Map && b is Map) {
    return a.length == b.length &&
        a.keys.every((key) => b.containsKey(key) && _same(a[key], b[key]));
  }
  return a == b;
}

void _uuid(Object? value) {
  if (value is! String || !validOfflineUuid(value)) _bad();
}

void _name(Object? value) {
  if (value is! String || offlineText(value, 200) != value) _bad();
}

DateTime _time(Object? value) {
  if (value is! String) _bad();
  final match = RegExp(
    r'^([1-9][0-9]{3}-[0-9]{2}-[0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]{1,6})?(Z|[+-]([0-9]{2}):([0-9]{2}))$',
  ).firstMatch(value);
  if (match == null ||
      !validOfflineDate(match.group(1)!) ||
      int.parse(match.group(2)!) > 23 ||
      int.parse(match.group(3)!) > 59 ||
      int.parse(match.group(4)!) > 59 ||
      (match.group(5) != 'Z' &&
          (int.parse(match.group(6)!) > 23 ||
              int.parse(match.group(7)!) > 59))) {
    _bad();
  }
  final parsed = DateTime.tryParse(value);
  if (parsed == null ||
      parsed.toUtc().year < 1000 ||
      parsed.toUtc().year > 9999) {
    _bad();
  }
  return parsed.toUtc();
}

const _fields = [
  'driver_name',
  'helper_name',
  'audit_date',
  'station',
  'plate_number',
  'remarks',
];
const _snapshotKeys = [
  'id',
  'profile_id',
  'audited_by_name',
  'created_at',
  'updated_at',
  'revision',
  'archived_at',
  ..._fields,
];
void _snapshot(Map<String, Object?> row) {
  if (row.length != _snapshotKeys.length ||
      !_snapshotKeys.every(row.containsKey)) {
    _bad();
  }
  _uuid(row['id']);
  _uuid(row['profile_id']);
  _name(row['audited_by_name']);
  final normalized = AuditValues.fromJson({
    for (final key in _fields) key: row[key],
  }).toJson();
  if (!_fields.every((key) => row[key] == normalized[key])) _bad();
  if (row['revision'] is! int || (row['revision'] as int) < 1) _bad();
  _time(row['created_at']);
  _time(row['updated_at']);
  if (row['archived_at'] != null) _time(row['archived_at']);
}

Set<String> _validateRows(Map<String, List<Map<String, Object?>>> rows) {
  try {
    final identities = <String>{};
    final profiles = rows['local_profile']!;
    if (profiles.length > 1) _bad();
    for (final profile in profiles) {
      if (profile['singleton'] != 1) _bad();
      _uuid(profile['id']);
      _name(profile['name']);
      identities.add(profile['id'] as String);
    }
    final groupedEvents = <Object?, List<Map<String, Object?>>>{};
    for (final event in rows['audit_events']!) {
      groupedEvents.putIfAbsent(event['audit_id'], () => []).add(event);
    }
    final records = rows['audit_records']!;
    var eventCount = 0;
    for (final row in records) {
      if (row['seq'] is! int || (row['seq'] as int) < 1) _bad();
      final current = Map<String, Object?>.from(row)..remove('seq');
      _snapshot(current);
      identities.add(row['profile_id'] as String);
      final events = groupedEvents[row['id']] ?? <Map<String, Object?>>[];
      eventCount += events.length;
      if (events.length != row['revision']) _bad();
      Map<String, Object?>? previous;
      for (var i = 0; i < events.length; i++) {
        final event = events[i];
        _uuid(event['id']);
        _uuid(event['actor_profile_id']);
        _name(event['actor_name']);
        identities.add(event['actor_profile_id'] as String);
        final before = event['before_json'] == null
            ? null
            : _inner(event['before_json'] as String);
        final after = Map<String, Object?>.from(
          _inner(event['after_json'] as String) as Map,
        );
        _snapshot(after);
        if (!_same(before, previous) ||
            event['revision'] != i + 1 ||
            after['revision'] != i + 1 ||
            after['id'] != row['id'] ||
            _time(event['created_at']) != _time(after['updated_at'])) {
          _bad();
        }
        if (i == 0) {
          if (event['action'] != 'CREATE' ||
              after['archived_at'] != null ||
              _time(after['created_at']) != _time(after['updated_at']) ||
              event['actor_profile_id'] != after['profile_id'] ||
              event['actor_name'] != after['audited_by_name']) {
            _bad();
          }
        } else {
          if (previous!['archived_at'] != null ||
              ![
                'id',
                'profile_id',
                'audited_by_name',
                'created_at',
              ].every((key) => previous![key] == after[key])) {
            _bad();
          }
          if (event['action'] == 'ARCHIVE') {
            if (after['archived_at'] == null ||
                _time(after['archived_at']) != _time(after['updated_at']) ||
                !_fields.every((key) => previous![key] == after[key])) {
              _bad();
            }
          } else if (event['action'] != 'UPDATE' ||
              after['archived_at'] != null ||
              _fields.every((key) => previous![key] == after[key])) {
            _bad();
          }
        }
        previous = after;
      }
      if (!_same(previous, current)) _bad();
    }
    if (rows['audit_events']!.length != eventCount) {
      _bad();
    }
    {
      final registry = rows['auditor_identities']!;
      for (final identity in registry) {
        _uuid(identity['id']);
      }
      if (!registry.map((row) => row['id']).toSet().containsAll(identities)) {
        _bad();
      }
      for (final receipt in rows['transfer_receipts']!) {
        _uuid(receipt['package_id']);
        _uuid(receipt['source_installation_id']);
        _time(receipt['imported_at']);
        if (receipt['content_sha256'] is! String ||
            !RegExp(r'^[0-9a-f]{64}$')
                .hasMatch(receipt['content_sha256'] as String) ||
            receipt['imported_count'] is! int ||
            (receipt['imported_count'] as int) < 0) {
          _bad();
        }
      }
    }
    return identities;
  } on OfflineFailure {
    _bad();
  } on FormatException {
    _bad();
  } on TypeError {
    _bad();
  }
}

const _columns = <String, String>{
  'app_meta': 'key value',
  'local_profile': 'singleton id name',
  'auditor_identities': 'id',
  'audit_records': 'seq id profile_id driver_name helper_name audit_date station plate_number remarks audited_by_name created_at updated_at revision archived_at',
  'audit_events': 'id audit_id revision action actor_name actor_profile_id created_at before_json after_json',
  'transfer_receipts': 'package_id content_sha256 source_installation_id imported_at imported_count',
};
const _ceilings = {
  'app_meta': 2,
  'local_profile': 1,
  'auditor_identities': 40001,
  'audit_records': 20000,
  'audit_events': 100000,
  'transfer_receipts': 20000,
};
String _appId(String platform) {
  if (platform == 'android') return 'com.bhli.audit.offline';
  if (platform == 'windows') return 'com.bhli.audit.offline.windows';
  _bad();
}

void _keys(Map value, Iterable<String> keys) =>
    _need(value.length == keys.length && keys.every(value.containsKey));
void _metadata(Map<String, Object?> m, String platform) {
  _keys(m, [
    'kind',
    'payload_version',
    'schema_version',
    'platform',
    'app_id',
    'backup_id',
    'created_at',
    'source_version',
    'counts',
    'sqlite_sequence_audit_records',
  ]);
  _need(
    m['kind'] == 'metadata' &&
        m['payload_version'] is int &&
        m['payload_version'] == 1 &&
        m['schema_version'] is int &&
        m['schema_version'] == 2 &&
        m['platform'] == platform &&
        m['app_id'] == _appId(platform),
  );
  _uuid(m['backup_id']);
  final created = m['created_at'];
  _need(
    created is String &&
        RegExp(
          r'^[1-9][0-9]{3}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$',
        ).hasMatch(created),
  );
  _time(created);
  final version = m['source_version'];
  _need(
    version is String &&
        version.isNotEmpty &&
        version.runes.length <= 64 &&
        !version.runes.any((r) => r < 32 || (r >= 127 && r <= 159)),
  );
  _need(m['counts'] is Map);
  _keys(m['counts'] as Map, _columns.keys);
  _canonical(m);
}

Map<String, List<Map<String, Object?>>> _checked(
  Map<String, List<Map<String, Object?>>> input,
  String platform,
  int? sequence,
) {
  _keys(input, _columns.keys);
  final rows = <String, List<Map<String, Object?>>>{};
  for (final table in _columns.keys) {
    final list = input[table]!;
    _need(list.length <= _ceilings[table]!);
    rows[table] = list.map((r) => Map<String, Object?>.from(r)).toList();
    final unique = <Object?>{}, eventPairs = <String>{};
    final primary = table == 'app_meta'
        ? 'key'
        : table == 'audit_records'
        ? 'seq'
        : table == 'transfer_receipts'
        ? 'package_id'
        : 'id';
    for (final row in list) {
      _keys(row, _columns[table]!.split(' '));
      _canonical(row);
      _need(unique.add(row[primary]));
      if (table == 'audit_events') {
        _need(row['before_json'] == null || row['before_json'] is String);
        _need(
          row['after_json'] is String &&
              eventPairs.add('${row['audit_id']}:${row['revision']}'),
        );
      }
    }
    rows[table]!.sort((a, b) {
      if (table == 'audit_records') {
        return (a['seq'] as int).compareTo(b['seq'] as int);
      }
      if (table == 'audit_events') {
        final c = (a['audit_id'] as String).compareTo(b['audit_id'] as String);
        return c != 0
            ? c
            : (a['revision'] as int).compareTo(b['revision'] as int);
      }
      return (a[primary] as String).compareTo(b[primary] as String);
    });
  }
  final meta = {for (final r in rows['app_meta']!) r['key']: r['value']};
  _need(meta.length == 2 && meta['app_id'] == _appId(platform));
  _uuid(meta['installation_id']);
  final maxSeq = rows['audit_records']!.isEmpty
      ? 0
      : rows['audit_records']!.last['seq'] as int;
  _need(
    (sequence == null && maxSeq == 0) ||
        (sequence != null && sequence >= maxSeq && sequence >= 0),
  );
  _need(
    rows['audit_records']!.map((r) => r['id']).toSet().length ==
        rows['audit_records']!.length,
  );
  _validateRows(rows);
  return rows;
}

List<int> _line(Map value) {
  final bytes = ascii.encode('${_canonical(value)}\n');
  _need(bytes.length <= 1024 * 1024);
  return bytes;
}

List<List<int>> _rowLines(Map<String, List<Map<String, Object?>>> rows) => [
  for (final table in _columns.keys)
    for (final row in rows[table]!) _line({'kind': table, 'row': row}),
];
String _digest(List<List<int>> lines, String platform, int? sequence) {
  final data = BytesBuilder(copy: false)
    ..add(ascii.encode('BHLI-STATE-v1\n'))
    ..add(
      _line({
        'app_id': _appId(platform),
        'platform': platform,
        'schema_version': 2,
        'sequence': sequence,
      }),
    );
  for (final line in lines) {
    _need(data.length + line.length <= _max);
    data.add(line);
  }
  return sha256.convert(data.takeBytes()).toString();
}

Uint8List encodeBackupState(
  Map<String, List<Map<String, Object?>>> input, {
  required String platform,
  required String backupId,
  required String createdAt,
  required String sourceVersion,
  int? sequence,
}) {
  try {
    final rows = _checked(input, platform, sequence);
    final metadata = <String, Object?>{
      'kind': 'metadata',
      'payload_version': 1,
      'schema_version': 2,
      'platform': platform,
      'app_id': _appId(platform),
      'backup_id': backupId,
      'created_at': createdAt,
      'source_version': sourceVersion,
      'counts': {for (final t in _columns.keys) t: rows[t]!.length},
      'sqlite_sequence_audit_records': sequence,
    };
    _metadata(metadata, platform);
    final lines = _rowLines(rows),
        out = BytesBuilder(copy: false)..add(_line(metadata));
    for (final line in lines) {
      _need(out.length + line.length <= _max);
      out.add(line);
    }
    final end = _line({
      'kind': 'end',
      'rows': rows.values.fold<int>(0, (n, r) => n + r.length),
      'content_bytes': out.length,
      'state_sha256': _digest(lines, platform, sequence),
    });
    _need(out.length + end.length <= _max);
    out.add(end);
    return out.takeBytes();
  } on FormatException {
    rethrow;
  } on Object {
    _bad();
  }
}

BackupState decodeBackupState(Uint8List bytes, {required String platform}) {
  try {
    _need(bytes.isNotEmpty && bytes.length <= _max && bytes.last == 10);
    final records = <Map<String, Object?>>[], ends = <int>[];
    var start = 0;
    for (var i = 0; i < bytes.length; i++) {
      _need(i - start < 1024 * 1024);
      if (bytes[i] != 10) continue;
      _need(i > start && records.length < 180006);
      final text = utf8.decode(
        Uint8List.sublistView(bytes, start, i),
        allowMalformed: false,
      );
      final parser = _Json(text), value = parser.value();
      _need(
        parser.p == text.length &&
            value is Map<String, dynamic> &&
            _canonical(value) == text,
      );
      records.add(Map<String, Object?>.from(value as Map));
      ends.add(i + 1);
      start = i + 1;
    }
    _need(records.length >= 2 && start == bytes.length);
    final metadata = records.first;
    _metadata(metadata, platform);
    final watermark = metadata['sqlite_sequence_audit_records'];
    _need(watermark == null || watermark is int);
    final rows = {for (final t in _columns.keys) t: <Map<String, Object?>>[]};
    var previous = -1;
    for (final envelope in records.skip(1).take(records.length - 2)) {
      _keys(envelope, ['kind', 'row']);
      final kind = envelope['kind'];
      _need(kind is String && rows.containsKey(kind));
      final index = _columns.keys.toList().indexOf(kind as String);
      _need(index >= previous);
      previous = index;
      _need(envelope['row'] is Map);
      rows[kind]!.add(Map<String, Object?>.from(envelope['row'] as Map));
      _need(rows[kind]!.length <= _ceilings[kind]!);
    }
    final checked = _checked(rows, platform, watermark as int?);
    final lines = _rowLines(checked);
    // Ensure exact source ordering, not merely the same sorted logical state.
    for (var i = 0; i < lines.length; i++) {
      _need(_canonical(records[i + 1]) == ascii.decode(lines[i]).trimRight());
    }
    final counts = metadata['counts'] as Map;
    for (final t in _columns.keys) {
      _need(counts[t] is int && counts[t] == rows[t]!.length);
    }
    final end = records.last;
    _keys(end, ['kind', 'rows', 'content_bytes', 'state_sha256']);
    final digest = _digest(lines, platform, watermark);
    _need(
      end['kind'] == 'end' &&
          end['rows'] is int &&
          end['rows'] == lines.length &&
          end['content_bytes'] is int &&
          end['content_bytes'] == ends[ends.length - 2] &&
          end['state_sha256'] == digest,
    );
    return BackupState(
      rows: checked,
      metadata: metadata,
      sequence: watermark,
      platform: platform,
      digest: digest,
    );
  } on FormatException {
    rethrow;
  } on Object {
    _bad();
  }
}
