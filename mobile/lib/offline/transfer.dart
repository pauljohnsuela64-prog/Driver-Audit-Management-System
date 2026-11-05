import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

import 'models.dart';

const _max = 32 * 1024 * 1024;
const _names = ['manifest.json', 'audits.ndjson', 'events.ndjson'];
Never _bad() => throw const FormatException(
  'Invalid transfer package. Narrow the date range if the package exceeds transfer limits.',
);
void _need(bool ok) {
  if (!ok) _bad();
}

class TransferPackage {
  TransferPackage(this.manifest, this.audits, this.events, this.contentSha256);
  final Map<String, dynamic> manifest;
  final List<Map<String, dynamic>> audits, events;
  final String contentSha256;
}

String canonicalJson(Object? value) {
  String emit(Object? v, int depth) {
    if (depth > 6) _bad();
    if (v == null || v is bool) return '$v';
    if (v is int) {
      _need(v >= 0 && v <= 9007199254740991);
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

// Parse objects before jsonDecode can discard duplicate member names.
class _Json {
  _Json(this.s);
  final String s;
  int p = 0;
  Object? value([int depth = 0]) {
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
          canonicalJson(v);
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
      if (p < s.length && s[p] == (object ? '}' : ']')) {
        p++;
        return object ? map : list;
      }
      while (true) {
        if (object) {
          final key = value(depth + 1);
          _need(key is String && !map.containsKey(key));
          _need(p < s.length && s[p++] == ':');
          map[key as String] = value(depth + 1);
        } else {
          list.add(value(depth + 1));
        }
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
    _need(n != null && n <= 9007199254740991);
    return n;
  }
}

Map<String, dynamic> _parse(List<int> bytes) {
  final s = utf8.decode(bytes, allowMalformed: false);
  final parser = _Json(s);
  final v = parser.value();
  _need(
    parser.p == s.length && v is Map<String, dynamic> && canonicalJson(v) == s,
  );
  return v as Map<String, dynamic>;
}

String _hash(List<int> b) => sha256.convert(b).toString();

class _DigestSink implements Sink<Digest> {
  late Digest digest;
  @override
  void add(Digest value) {
    digest = value;
  }

  @override
  void close() {}
}

String _hashParts(List<Uint8List> parts) {
  final result = _DigestSink();
  final sink = sha256.startChunkedConversion(result);
  for (final part in parts) {
    sink.add(part);
  }
  sink.close();
  return result.digest.toString();
}

void _keys(Map m, String names) {
  final set = names.split(' ').toSet();
  _need(m.length == set.length && m.keys.every(set.contains));
}

void _uuid(Object? v) => _need(v is String && validOfflineUuid(v));
void _time(Object? v) {
  _need(
    v is String &&
        RegExp(
          r'^[1-9][0-9]{3}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$',
        ).hasMatch(v),
  );
  final s = v as String;
  _need(
    validOfflineDate(s.substring(0, 10)) &&
        int.parse(s.substring(11, 13)) < 24 &&
        int.parse(s.substring(14, 16)) < 60 &&
        int.parse(s.substring(17, 19)) < 60,
  );
}

const _editable = [
  'driver_name',
  'helper_name',
  'audit_date',
  'station',
  'plate_number',
  'remarks',
];
void _audit(Map<String, dynamic> a) {
  _keys(
    a,
    'driver_name helper_name audit_date station plate_number remarks id profile_id audited_by_name created_at updated_at revision archived_at',
  );
  _uuid(a['id']);
  _uuid(a['profile_id']);
  _time(a['created_at']);
  _time(a['updated_at']);
  if (a['archived_at'] != null) _time(a['archived_at']);
  _need(
    a['revision'] is int &&
        a['revision'] >= 1 &&
        a['revision'] <= 9007199254740991,
  );
  final values = AuditValues.fromJson({for (final k in _editable) k: a[k]});
  _need(
    canonicalJson(values.toJson()) ==
        canonicalJson({for (final k in _editable) k: a[k]}),
  );
  _need(
    a['audited_by_name'] is String &&
        offlineText(a['audited_by_name'], 200) == a['audited_by_name'],
  );
}

void _validate(
  Map<String, dynamic> m,
  List<Map<String, dynamic>> audits,
  List<Map<String, dynamic>> events,
) {
  _keys(
    m,
    'format format_version package_id source_installation_id exported_at record_count event_count filters audits_sha256 events_sha256',
  );
  _need(
    m['format'] == 'bhli-audit-transfer' &&
        m['format_version'] is int &&
        m['format_version'] == 1,
  );
  _uuid(m['package_id']);
  _uuid(m['source_installation_id']);
  _time(m['exported_at']);
  _need(
    audits.length <= 2000 &&
        events.length <= 10000 &&
        m['record_count'] is int &&
        m['record_count'] == audits.length &&
        m['event_count'] is int &&
        m['event_count'] == events.length,
  );
  for (final key in ['audits_sha256', 'events_sha256']) {
    _need(m[key] is String && RegExp(r'^[0-9a-f]{64}$').hasMatch(m[key]));
  }
  final f = m['filters'];
  _need(f is Map);
  _keys(f as Map, 'date_from date_to include_archived');
  _need(f['include_archived'] == true);
  for (final k in ['date_from', 'date_to']) {
    _need(f[k] == null || (f[k] is String && validOfflineDate(f[k])));
  }
  _need(
    f['date_from'] == null ||
        f['date_to'] == null ||
        (f['date_from'] as String).compareTo(f['date_to']) <= 0,
  );
  final byId = <String, Map<String, dynamic>>{};
  String last = '';
  for (final a in audits) {
    _audit(a);
    final id = a['id'] as String;
    _need(id.compareTo(last) > 0);
    last = id;
    byId[id] = a;
    _need(
      (f['date_from'] == null ||
              (a['audit_date'] as String).compareTo(f['date_from']) >= 0) &&
          (f['date_to'] == null ||
              (a['audit_date'] as String).compareTo(f['date_to']) <= 0),
    );
  }
  final previous = <String, Map<String, dynamic>>{};
  final ids = <String>{};
  String lastAudit = '';
  int lastRevision = 0;
  for (final e in events) {
    _keys(
      e,
      'id audit_id revision action actor_name actor_profile_id created_at before after',
    );
    _uuid(e['id']);
    _uuid(e['audit_id']);
    _uuid(e['actor_profile_id']);
    _time(e['created_at']);
    _need(
      ids.add(e['id']) &&
          e['actor_name'] is String &&
          offlineText(e['actor_name'], 200) == e['actor_name'],
    );
    final id = e['audit_id'] as String;
    final rev = e['revision'];
    _need(
      byId.containsKey(id) && rev is int && rev >= 1 && rev <= 9007199254740991,
    );
    _need(
      id.compareTo(lastAudit) > 0 || (id == lastAudit && rev > lastRevision),
    );
    lastAudit = id;
    lastRevision = rev as int;
    _need(e['after'] is Map<String, dynamic>);
    final after = e['after'] as Map<String, dynamic>;
    _audit(after);
    _need(
      after['id'] == id &&
          after['revision'] == rev &&
          after['updated_at'] == e['created_at'],
    );
    final prior = previous[id];
    if (prior == null) {
      _need(
        rev == 1 &&
            e['action'] == 'CREATE' &&
            e['before'] == null &&
            after['archived_at'] == null &&
            after['created_at'] == e['created_at'] &&
            after['profile_id'] == e['actor_profile_id'] &&
            after['audited_by_name'] == e['actor_name'],
      );
    } else {
      _need(e['before'] is Map<String, dynamic>);
      final before = e['before'] as Map<String, dynamic>;
      _audit(before);
      _need(
        canonicalJson(before) == canonicalJson(prior) &&
            rev == prior['revision'] + 1 &&
            prior['archived_at'] == null,
      );
      final action = e['action'];
      _need(action == 'UPDATE' || action == 'ARCHIVE');
      final allowed = action == 'UPDATE'
          ? {..._editable, 'revision', 'updated_at'}
          : {'revision', 'updated_at', 'archived_at'};
      for (final k in after.keys) {
        if (!allowed.contains(k)) _need(after[k] == prior[k]);
      }
      if (action == 'UPDATE') {
        _need(_editable.any((k) => after[k] != prior[k]));
      } else {
        _need(after['archived_at'] == e['created_at']);
      }
    }
    previous[id] = after;
  }
  for (final a in audits) {
    _need(
      previous.containsKey(a['id']) &&
          canonicalJson(previous[a['id']]) == canonicalJson(a),
    );
  }
}

int _crc(List<int> bytes) {
  var c = 0xffffffff;
  for (final b in bytes) {
    c ^= b;
    for (var j = 0; j < 8; j++) {
      c = (c >> 1) ^ ((c & 1) != 0 ? 0xedb88320 : 0);
    }
  }
  return (c ^ 0xffffffff) & 0xffffffff;
}

Uint8List _zip(List<Uint8List> data) {
  final out = BytesBuilder(copy: false), central = BytesBuilder(copy: false);
  int offset = 0;
  for (var i = 0; i < 3; i++) {
    final name = ascii.encode(_names[i]), bytes = data[i], crc = _crc(bytes);
    final h = ByteData(30)
      ..setUint32(0, 0x04034b50, Endian.little)
      ..setUint16(4, 20, Endian.little)
      ..setUint16(12, 33, Endian.little)
      ..setUint32(14, crc, Endian.little)
      ..setUint32(18, bytes.length, Endian.little)
      ..setUint32(22, bytes.length, Endian.little)
      ..setUint16(26, name.length, Endian.little);
    out.add(h.buffer.asUint8List());
    out.add(name);
    out.add(bytes);
    final c = ByteData(46)
      ..setUint32(0, 0x02014b50, Endian.little)
      ..setUint16(4, 788, Endian.little)
      ..setUint16(6, 20, Endian.little)
      ..setUint16(14, 33, Endian.little)
      ..setUint32(16, crc, Endian.little)
      ..setUint32(20, bytes.length, Endian.little)
      ..setUint32(24, bytes.length, Endian.little)
      ..setUint16(28, name.length, Endian.little)
      ..setUint32(38, 0x01800000, Endian.little)
      ..setUint32(42, offset, Endian.little);
    central.add(c.buffer.asUint8List());
    central.add(name);
    offset += 30 + name.length + bytes.length;
  }
  final c = central.takeBytes();
  out.add(c);
  final e = ByteData(22)
    ..setUint32(0, 0x06054b50, Endian.little)
    ..setUint16(8, 3, Endian.little)
    ..setUint16(10, 3, Endian.little)
    ..setUint32(12, c.length, Endian.little)
    ..setUint32(16, offset, Endian.little);
  out.add(e.buffer.asUint8List());
  final result = out.takeBytes();
  _need(result.length <= _max);
  return result;
}

List<Uint8List> _unzip(Uint8List b) {
  _need(b.length >= 22 && b.length <= _max);
  final d = ByteData.sublistView(b);
  int u16(int p) => d.getUint16(p, Endian.little);
  int u32(int p) => d.getUint32(p, Endian.little);
  final end = b.length - 22;
  _need(
    u32(end) == 0x06054b50 &&
        u16(end + 4) == 0 &&
        u16(end + 6) == 0 &&
        u16(end + 8) == 3 &&
        u16(end + 10) == 3 &&
        u16(end + 20) == 0,
  );
  var cp = u32(end + 16);
  _need(cp + u32(end + 12) == end);
  var lp = 0, total = 0;
  final result = <Uint8List>[];
  for (var i = 0; i < 3; i++) {
    _need(cp + 46 <= end && u32(cp) == 0x02014b50);
    final n = u16(cp + 28), sz = u32(cp + 24), crc = u32(cp + 16);
    _need(
      u16(cp + 6) <= 20 &&
          (u16(cp + 8) == 0 || u16(cp + 8) == 0x800) &&
          u16(cp + 10) == 0 &&
          u32(cp + 20) == sz &&
          u16(cp + 30) == 0 &&
          u16(cp + 32) == 0 &&
          u16(cp + 34) == 0 &&
          u16(cp + 36) == 0 &&
          u32(cp + 42) == lp,
    );
    final attrs = u32(cp + 38);
    _need(
      (attrs & 0x10) == 0 &&
          (((attrs >> 16) & 0xf000) == 0 || ((attrs >> 16) & 0xf000) == 0x8000),
    );
    _need(
      cp + 46 + n <= end &&
          ascii.decode(b.sublist(cp + 46, cp + 46 + n)) == _names[i],
    );
    _need(
      lp + 30 <= u32(end + 16) &&
          u32(lp) == 0x04034b50 &&
          u16(lp + 4) == u16(cp + 6) &&
          u16(lp + 6) == u16(cp + 8) &&
          u16(lp + 8) == 0 &&
          u16(lp + 10) == u16(cp + 12) &&
          u16(lp + 12) == u16(cp + 14) &&
          u32(lp + 14) == crc &&
          u32(lp + 18) == sz &&
          u32(lp + 22) == sz &&
          u16(lp + 26) == n &&
          u16(lp + 28) == 0,
    );
    _need(
      lp + 30 + n + sz <= u32(end + 16) &&
          ascii.decode(b.sublist(lp + 30, lp + 30 + n)) == _names[i],
    );
    total += sz;
    _need(total <= _max && (i != 0 || sz <= 65536));
    final bytes = Uint8List.sublistView(b, lp + 30 + n, lp + 30 + n + sz);
    _need(_crc(bytes) == crc);
    result.add(bytes);
    lp += 30 + n + sz;
    cp += 46 + n;
  }
  _need(lp == u32(end + 16) && cp == end);
  return result;
}

Uint8List _rows(List<Map<String, dynamic>> rows) {
  final b = BytesBuilder(copy: false);
  for (final r in rows) {
    final line = ascii.encode('${canonicalJson(r)}\n');
    _need(line.length <= 262144 && b.length + line.length <= _max);
    b.add(line);
  }
  return b.takeBytes();
}

List<Map<String, dynamic>> _readRows(Uint8List b, int limit) {
  final rows = <Map<String, dynamic>>[];
  var start = 0;
  for (var i = 0; i < b.length; i++) {
    _need(i - start < 262144);
    if (b[i] == 10) {
      _need(rows.length < limit && i > start);
      rows.add(_parse(Uint8List.sublistView(b, start, i)));
      start = i + 1;
    }
  }
  _need(start == b.length);
  return rows;
}

Uint8List encodeTransfer(
  Map<String, dynamic> manifest,
  List<Map<String, dynamic>> audits,
  List<Map<String, dynamic>> events,
) {
  try {
    _need(audits.length <= 2000 && events.length <= 10000);
    final a = [...audits]
      ..sort((a, b) => (a['id'] as String).compareTo(b['id'] as String));
    final e = [...events]
      ..sort((a, b) {
        final c = (a['audit_id'] as String).compareTo(b['audit_id'] as String);
        return c != 0
            ? c
            : (a['revision'] as int).compareTo(b['revision'] as int);
      });
    _validate(
      {
        ...manifest,
        'record_count': a.length,
        'event_count': e.length,
        'audits_sha256': '0' * 64,
        'events_sha256': '0' * 64,
      },
      a,
      e,
    );
    final ab = _rows(a), eb = _rows(e);
    final m = <String, dynamic>{
      ...manifest,
      'record_count': a.length,
      'event_count': e.length,
      'audits_sha256': _hash(ab),
      'events_sha256': _hash(eb),
    };
    _validate(m, a, e);
    final mb = Uint8List.fromList(ascii.encode('${canonicalJson(m)}\n'));
    _need(mb.length <= 65536 && mb.length + ab.length + eb.length <= _max);
    return _zip([mb, ab, eb]);
  } catch (e) {
    if (e is FormatException) rethrow;
    _bad();
  }
}

TransferPackage decodeTransfer(Uint8List bytes) {
  try {
    final data = _unzip(bytes), mb = data[0];
    _need(mb.isNotEmpty && mb.last == 10);
    final m = _parse(Uint8List.sublistView(mb, 0, mb.length - 1)),
        a = _readRows(data[1], 2000),
        e = _readRows(data[2], 10000);
    _need(
      m['audits_sha256'] == _hash(data[1]) &&
          m['events_sha256'] == _hash(data[2]),
    );
    _validate(m, a, e);
    return TransferPackage(m, a, e, _hashParts(data));
  } catch (e) {
    if (e is FormatException) rethrow;
    _bad();
  }
}
