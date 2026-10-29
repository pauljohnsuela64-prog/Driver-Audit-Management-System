import 'dart:convert';

import 'package:bhli_audit/core/network/api_client.dart';
import 'package:bhli_audit/core/network/api_failure.dart';
import 'package:bhli_audit/core/network/api_origin.dart';
import 'package:bhli_audit/features/audits/audit_draft.dart';
import 'package:bhli_audit/features/audits/models.dart';
import 'package:bhli_audit/features/auth/models.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'network_test_support.dart';
import 'audit_history_contract_test.dart' show historyEvent;

void main() {
  final requests = <http.BaseRequest>[];
  late http.StreamedResponse Function(http.BaseRequest) reply;
  late ApiClient api;
  final draft = AuditDraft(
    driverName: ' Driver ',
    auditDate: '2026-10-28',
    station: 'Station',
    plateNumber: '000123',
  );
  setUp(() {
    requests.clear();
    reply = (_) => jsonResponse(auditJson(), headers: {'etag': '"3"'});
    api = ApiClient(
      ApiOrigin.parse('https://example.com'),
      clientFactory: () => RecordingClient((r) {
        requests.add(r);
        return reply(r);
      }),
    );
  });
  test('same plate is allowed across distinct create attempts', () async {
    var id = 0;
    reply = (_) => jsonResponse(
      {...auditJson(id: ++id), 'plate_number': '000123'},
      status: 201,
      headers: {'etag': '"3"'},
    );
    final first = PendingAuditCreate(draft);
    final second = PendingAuditCreate(draft);
    expect(first.key, isNot(second.key));
    expect((await api.createAudit(tokenA, first)).record.id, 1);
    expect((await api.createAudit(tokenA, second)).record.id, 2);
    expect(
      requests.map((r) => jsonDecode((r as http.Request).body)['plate_number']),
      ['000123', '000123'],
    );
  });
  test(
    'archived list access is explicit and active-only remains strict',
    () async {
      final archived = {
        ...auditJson(),
        'deleted_at': '2026-10-28T00:00:00Z',
        'deleted_by_user_id': 9,
      };
      reply = (_) => jsonResponse({
        'items': [archived],
        'page': 1,
        'page_size': 25,
        'total': 1,
      });
      await expectLater(
        api.audits(tokenA, AuditQuery()),
        throwsA(isA<ApiFailure>()),
      );
      expect(
        requests.last.url.queryParameters.containsKey('include_deleted'),
        false,
      );
      final mode = AuditAccess.archivedFor(
        AuthenticatedUser.fromJson(userJson(role: 'ADMIN')),
      );
      final result = await api.audits(tokenA, AuditQuery(), access: mode);
      expect(result.items.single.deletedByUserId, 9);
      expect(requests.last.url.queryParameters['include_deleted'], 'true');
    },
  );
  test('backend-valid BOM-only audit text survives response parsing', () async {
    reply = (_) => jsonResponse(
      {...auditJson(), 'driver_name': '\ufeff'},
      headers: {'etag': '"3"'},
    );
    expect(
      (await api.createAudit(
        tokenA,
        PendingAuditCreate(draft),
      )).record.driverName,
      '\ufeff',
    );
  });
  test(
    'create freezes nullable six-field payload and accepts 201 or 200 replay',
    () async {
      final attempt = PendingAuditCreate(draft);
      for (final status in [201, 200]) {
        reply = (_) =>
            jsonResponse(auditJson(), status: status, headers: {'etag': '"3"'});
        final result = await api.createAudit(tokenA, attempt);
        expect(result.replayed, status == 200);
        expect(result.record.version, 3);
        final r = requests.last as http.Request;
        expect(r.method, 'POST');
        expect(r.url.path, '/audits');
        expect(r.headers['idempotency-key'], attempt.key);
        expect(r.headers['authorization'], 'Bearer $tokenA');
        expect(jsonDecode(r.body), draft.toCreateJson());
        expect(jsonDecode(r.body)['helper_name'], isNull);
        expect(r.followRedirects, false);
      }
    },
  );
  test('PATCH uses exact ETag and nullable changed-only typed payload; DELETE expects204', () async {
    reply = (_) =>
        jsonResponse({...auditJson(), 'version': 4}, headers: {'etag': '"4"'});
    final result = await api.updateAudit(
      tokenA,
      1,
      '"3"',
      AuditPatch.fromJson({'helper_name': null}),
    );
    expect(result.version, 4);
    final patch = requests.last as http.Request;
    expect(patch.method, 'PATCH');
    expect(patch.headers['if-match'], '"3"');
    expect(jsonDecode(patch.body), {'helper_name': null});
    reply = (_) => http.StreamedResponse(const Stream.empty(), 204);
    await api.deleteAudit(tokenA, 1, '"4"');
    expect(requests.last.method, 'DELETE');
    expect(requests.last.headers['if-match'], '"4"');
  });
  test('reject malformed IDs and ETags before transport', () async {
    for (final tag in [
      '3',
      'W/"3"',
      '"0"',
      '"03"',
      '"3"\r\nx:y',
      '"12345678901"',
    ]) {
      await expectLater(
        api.deleteAudit(tokenA, 1, tag),
        throwsA(isA<ApiFailure>()),
      );
    }
    await expectLater(
      api.deleteAudit(tokenA, 0, '"3"'),
      throwsA(isA<ApiFailure>()),
    );
    expect(requests, isEmpty);
  });
  test(
    'reject incorrect mutation status, record ID, version and ETag',
    () async {
      for (final response in [
        () => jsonResponse(auditJson(), status: 202, headers: {'etag': '"3"'}),
        () => jsonResponse(auditJson(id: 2), headers: {'etag': '"3"'}),
        () => jsonResponse(auditJson(), headers: {'etag': '"4"'}),
        () => jsonResponse(auditJson()),
      ]) {
        reply = (_) => response();
        await expectLater(
          api.updateAudit(
            tokenA,
            1,
            '"2"',
            AuditPatch.fromJson({'remarks': 'new'}),
          ),
          throwsA(isA<ApiFailure>()),
        );
      }
      reply = (_) => jsonResponse(auditJson(), headers: {'etag': '"3"'});
      await expectLater(
        api.updateAudit(
          tokenA,
          1,
          '"3"',
          AuditPatch.fromJson({'remarks': 'new'}),
        ),
        throwsA(isA<ApiFailure>()),
      );
    },
  );
  test('409 412 428 and auth failures retain safe actionable status', () async {
    for (final status in [401, 403, 409, 412, 428, 503]) {
      reply = (_) => jsonResponse({
        'password_hash': 'private server detail',
      }, status: status);
      await expectLater(
        api.createAudit(tokenA, PendingAuditCreate(draft)),
        throwsA(
          isA<ApiFailure>()
              .having((e) => e.status, 'status', status)
              .having(
                (e) => e.toString().contains('private'),
                'sanitized',
                false,
              ),
        ),
      );
    }
  });
  test(
    'history requests ten events and explicit ADMIN archived access only',
    () async {
      reply = (_) => jsonResponse({
        'items': [historyEvent()],
        'page': 1,
        'page_size': 10,
        'total': 1,
      });
      await api.auditHistory(tokenA, 1);
      expect(requests.last.url.queryParameters, {
        'page': '1',
        'page_size': '10',
      });
      final access = AuditAccess.archivedFor(
        AuthenticatedUser.fromJson(userJson(role: 'ADMIN')),
      );
      await api.auditHistory(tokenA, 1, access: access);
      expect(requests.last.url.queryParameters['include_deleted'], 'true');
      reply = (_) => jsonResponse(
        {
          ...auditJson(),
          'deleted_at': '2026-10-28T00:00:00Z',
          'deleted_by_user_id': 9,
        },
        headers: {'etag': '"3"'},
      );
      await expectLater(api.audit(tokenA, 1), throwsA(isA<ApiFailure>()));
      expect((await api.audit(tokenA, 1, access: access)).deletedByUserId, 9);
    },
  );
  test(
    'write failures retain existing redirect/body-size/transport safeguards',
    () async {
      for (final status in [301, 302, 307, 308]) {
        reply = (_) => jsonResponse(
          {},
          status: status,
          headers: {'location': 'https://other.example'},
        );
        await expectLater(
          api.createAudit(tokenA, PendingAuditCreate(draft)),
          throwsA(isA<ApiFailure>()),
        );
      }
      reply = (_) => http.StreamedResponse(
        Stream.value(List.filled(2 * 1024 * 1024 + 1, 32)),
        201,
      );
      await expectLater(
        api.createAudit(tokenA, PendingAuditCreate(draft)),
        throwsA(isA<ApiFailure>()),
      );
      reply = (_) => throw StateError('raw password token');
      await expectLater(
        api.createAudit(tokenA, PendingAuditCreate(draft)),
        throwsA(
          isA<ApiFailure>().having(
            (e) => e.code,
            'safe network failure',
            'network',
          ),
        ),
      );
    },
  );
}
