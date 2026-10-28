import 'dart:async';

import 'package:bhli_audit/core/network/api_client.dart';
import 'package:bhli_audit/core/network/api_failure.dart';
import 'package:bhli_audit/core/network/api_origin.dart';
import 'package:bhli_audit/features/audits/audit_draft.dart';
import 'package:bhli_audit/features/audits/audit_mutation_controller.dart';
import 'package:bhli_audit/features/audits/models.dart';
import 'package:bhli_audit/features/auth/models.dart';
import 'package:bhli_audit/features/auth/session_controller.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'network_test_support.dart';

// Deliberately uncancelable delegate proves generation guards independently of
// the real transport's cancellation race (including genuinely late 401/success).
class LateMutationApi extends ApiClient {
  LateMutationApi(super.origin, this.completion, this.onLogin, this.identity);
  final Completer<AuditMutationResult> completion;
  final SessionLease Function() onLogin;
  final AuthenticatedUser Function() identity;
  @override
  Future<SessionLease> login(String username, String password) async =>
      onLogin();
  @override
  Future<AuthenticatedUser> me(String token) async => identity();
  @override
  Future<void> logout(String token) async {}
  @override
  Future<AuditMutationResult> createAudit(
    String token,
    PendingAuditCreate attempt,
  ) => completion.future;
}

void main() {
  late SessionController session;
  late FutureOr<http.StreamedResponse> Function(http.BaseRequest) handler;
  late List<http.BaseRequest> requests;
  late DateTime now;
  var loginCount = 0;
  PendingAuditCreate attempt() => PendingAuditCreate(
    AuditDraft(
      driverName: 'Fictional',
      auditDate: '2026-10-28',
      station: 'Test',
      plateNumber: '0001',
    ),
  );
  setUp(() async {
    requests = [];
    now = DateTime.utc(2026, 10, 28, 12);
    loginCount = 0;
    handler = (_) => jsonResponse(auditJson(), headers: {'etag': '"3"'});
    session = SessionController(
      (origin) => ApiClient(
        origin,
        clientFactory: () => RecordingClient((r) {
          requests.add(r);
          if (r.url.path == '/auth/login') {
            return jsonResponse(
              leaseJson(token: loginCount++ == 0 ? tokenA : tokenB),
            );
          }
          if (r.url.path == '/auth/logout') {
            return http.StreamedResponse(const Stream.empty(), 204);
          }
          if (r.url.path == '/auth/me') return handler(r);
          return handler(r);
        }),
      ),
      clock: () => now,
    )..setOrigin(ApiOrigin.parse('https://example.com'));
    handler = (r) => r.url.path == '/auth/me'
        ? jsonResponse(userJson(role: 'ADMIN'))
        : jsonResponse(auditJson(), headers: {'etag': '"3"'});
    await session.signIn('fictional', 'password');
  });
  tearDown(() => session.dispose());
  Future<void> tick() => Future<void>.delayed(Duration.zero);
  Matcher mutationFailure = isA<AuditMutationFailure>();
  test('separate latch prevents double dispatch and read cancellation cannot abort save', () async {
    final pending = Completer<http.StreamedResponse>();
    handler = (_) => pending.future;
    final a = attempt();
    final saved = session.createAudit(a);
    await tick();
    expect(session.mutations.busy, true);
    expect(session.busy, false);
    await expectLater(session.createAudit(a), throwsA(mutationFailure));
    session.cancelAuditList();
    session.cancelAuditDetail();
    expect(
      requests
          .where((r) => r.method == 'POST' && r.url.path == '/audits')
          .length,
      1,
    );
    pending.complete(
      jsonResponse(auditJson(), status: 201, headers: {'etag': '"3"'}),
    );
    expect((await saved).record.id, 1);
    expect(session.mutations.state.phase, AuditMutationPhase.confirmed);
  });
  test('lost response retains frozen key, no automatic retry, edited replay accepted', () async {
    var calls = 0;
    final committedKeys = <String>{};
    handler = (r) {
      calls++;
      committedKeys.add(r.headers['idempotency-key']!);
      if (calls == 1) throw StateError('response lost after commit');
      return jsonResponse(
        {...auditJson(), 'driver_name': 'Edited later'},
        headers: {'etag': '"3"'},
      );
    };
    final a = attempt();
    await expectLater(session.createAudit(a), throwsA(mutationFailure));
    expect(session.mutations.state.phase, AuditMutationPhase.unknown);
    expect(session.mutations.pendingCreate, same(a));
    await tick();
    expect(calls, 1);
    await expectLater(session.createAudit(attempt()), throwsA(mutationFailure));
    expect(calls, 1);
    final result = await session.mutations.retryCreate();
    expect(result.replayed, true);
    expect(committedKeys.length, 1);
    expect(result.record.driverName, 'Edited later');
    final writes = requests
        .where((r) => r.url.path == '/audits')
        .cast<http.Request>()
        .toList();
    expect(writes.map((r) => r.headers['idempotency-key']).toSet(), {a.key});
    expect(writes.map((r) => r.body).toSet().length, 1);
    expect(session.mutations.pendingCreate, isNull);
  });
  test('409 never rotates key and abandonment requires explicit risk acknowledgment', () async {
    handler = (_) => jsonResponse({}, status: 409);
    final a = attempt();
    await expectLater(session.createAudit(a), throwsA(mutationFailure));
    expect(session.mutations.state.phase, AuditMutationPhase.conflict);
    expect(
      () => session.mutations.abandonCreate(acknowledgeDuplicateRisk: false),
      throwsA(mutationFailure),
    );
    expect(session.mutations.pendingCreate, same(a));
    session.mutations.abandonCreate(acknowledgeDuplicateRisk: true);
    expect(session.mutations.pendingCreate, isNull);
  });
  test('PATCH unknown retains precondition and blocks writes until explicit fresh review', () async {
    handler = (r) => r.method == 'PATCH'
        ? throw ApiFailure.timeout
        : jsonResponse(
            {...auditJson(), 'version': 4},
            headers: {'etag': '"4"'},
          );
    await expectLater(
      session.updateAudit(1, '"3"', AuditPatch.fromJson({'remarks': null})),
      throwsA(mutationFailure),
    );
    expect(session.mutations.state.etag, '"3"');
    expect(
      () => session.mutations.abandonCreate(acknowledgeDuplicateRisk: true),
      throwsA(mutationFailure),
    );
    expect(session.mutations.state.patch!.payload, {'remarks': null});
    expect(session.mutations.state.phase, AuditMutationPhase.unknown);
    await expectLater(session.deleteAudit(1, '"3"'), throwsA(mutationFailure));
    expect(requests.where((r) => r.method == 'PATCH').length, 1);
    expect((await session.reviewMutation()).version, 4);
    session.mutations.acknowledgeReview();
    expect(session.mutations.state.phase, AuditMutationPhase.idle);
  });
  test(
    'unknown DELETE reviews archived state explicitly without retrying delete',
    () async {
      handler = (r) => r.method == 'DELETE'
          ? throw ApiFailure.timeout
          : jsonResponse(
              {
                ...auditJson(),
                'deleted_at': '2026-10-28T12:00:00Z',
                'deleted_by_user_id': 8,
              },
              headers: {'etag': '"3"'},
            );
      await expectLater(
        session.deleteAudit(1, '"3"'),
        throwsA(mutationFailure),
      );
      expect((await session.reviewMutation()).deletedAt, isNotNull);
      expect(requests.last.url.queryParameters['include_deleted'], 'true');
      expect(requests.where((r) => r.method == 'DELETE').length, 1);
    },
  );
  test(
    'canceling a pending request is unknown, never claimed rollback',
    () async {
      final pending = Completer<http.StreamedResponse>();
      handler = (_) => pending.future;
      final result = expectLater(
        session.createAudit(attempt()),
        throwsA(mutationFailure),
      );
      await tick();
      session.cancelAuditMutation();
      await result;
      expect(session.mutations.state.phase, AuditMutationPhase.unknown);
      expect(session.mutations.pendingCreate, isNotNull);
      pending.complete(
        jsonResponse(auditJson(), status: 201, headers: {'etag': '"3"'}),
      );
    },
  );
  test('logout clears mutation state and old 401 cannot invalidate newer login or origin', () async {
    final pending = Completer<http.StreamedResponse>();
    handler = (r) => r.url.path == '/auth/me'
        ? jsonResponse(userJson(role: 'ADMIN'))
        : pending.future;
    final result = expectLater(
      session.createAudit(attempt()),
      throwsA(mutationFailure),
    );
    await tick();
    final logout = session.signOut();
    expect(session.user, isNull);
    expect(session.mutations.pendingCreate, isNull);
    await logout;
    await result;
    session.setOrigin(ApiOrigin.parse('https://new.example'));
    await session.signIn('other', 'password');
    pending.complete(jsonResponse({}, status: 401));
    await tick();
    expect(session.user, isNotNull);
    expect(session.mutations.state.phase, AuditMutationPhase.idle);
    expect(session.origin!.value, 'https://new.example');
  });
  test('mutation waits for resume verification and preserves logout during verification', () async {
    final identity = Completer<http.StreamedResponse>();
    handler = (r) => r.url.path == '/auth/me'
        ? identity.future
        : jsonResponse(auditJson(), status: 201, headers: {'etag': '"3"'});
    final resumed = session.verifyOnResume();
    await tick();
    final save = expectLater(
      session.createAudit(attempt()),
      throwsA(mutationFailure),
    );
    await tick();
    expect(requests.where((r) => r.url.path == '/audits'), isEmpty);
    await session.signOut();
    await save;
    await resumed;
    identity.complete(jsonResponse(userJson(role: 'ADMIN')));
    await tick();
    expect(session.user, isNull);
  });
  test('successful resume is awaited before save dispatch', () async {
    final identity = Completer<http.StreamedResponse>();
    handler = (r) => r.url.path == '/auth/me'
        ? identity.future
        : jsonResponse(auditJson(), status: 201, headers: {'etag': '"3"'});
    final resumed = session.verifyOnResume();
    await tick();
    final saved = session.createAudit(attempt());
    await tick();
    expect(requests.where((r) => r.url.path == '/audits'), isEmpty);
    identity.complete(jsonResponse(userJson(role: 'ADMIN')));
    await resumed;
    expect((await saved).record.id, 1);
  });
  test(
    'expiry clears keys and malformed success remains unconfirmed',
    () async {
      handler = (_) => jsonResponse({'invalid': 'success'}, status: 201);
      await expectLater(
        session.createAudit(attempt()),
        throwsA(mutationFailure),
      );
      expect(session.mutations.state.phase, AuditMutationPhase.unknown);
      now = DateTime.utc(2026, 10, 29);
      await expectLater(
        session.mutations.retryCreate(),
        throwsA(mutationFailure),
      );
      expect(session.user, isNull);
      expect(session.mutations.pendingCreate, isNull);
    },
  );
  test(
    'failed fresh review cannot reuse a previous successful review',
    () async {
      handler = (r) => r.method == 'PATCH'
          ? throw ApiFailure.timeout
          : jsonResponse(
              {...auditJson(), 'version': 4},
              headers: {'etag': '"4"'},
            );
      await expectLater(
        session.updateAudit(1, '"3"', AuditPatch.fromJson({'remarks': 'x'})),
        throwsA(mutationFailure),
      );
      await session.reviewMutation();
      expect(session.mutations.state.latest, isNotNull);
      handler = (_) => throw StateError('offline');
      await expectLater(session.reviewMutation(), throwsA(isA<ApiFailure>()));
      expect(session.mutations.state.latest, isNull);
      expect(session.mutations.acknowledgeReview, throwsA(mutationFailure));
    },
  );
  test('failed resume prevents a queued save from dispatching', () async {
    final identity = Completer<http.StreamedResponse>();
    handler = (r) => identity.future;
    final resumed = session.verifyOnResume();
    await tick();
    final save = expectLater(
      session.createAudit(attempt()),
      throwsA(mutationFailure),
    );
    await tick();
    identity.complete(jsonResponse({}, status: 401));
    await resumed;
    await save;
    expect(session.user, isNull);
    expect(session.mutations.pendingCreate, isNull);
    expect(requests.where((r) => r.url.path == '/audits'), isEmpty);
  });
  test(
    'expiry during write suppresses a late valid success and clears state',
    () async {
      final completion = Completer<http.StreamedResponse>();
      handler = (_) => completion.future;
      final result = expectLater(
        session.createAudit(attempt()),
        throwsA(mutationFailure),
      );
      await tick();
      now = DateTime.utc(2026, 10, 29);
      completion.complete(
        jsonResponse(auditJson(), status: 201, headers: {'etag': '"3"'}),
      );
      await result;
      expect(session.user, isNull);
      expect(session.mutations.pendingCreate, isNull);
      expect(session.mutations.state.record, isNull);
    },
  );
  for (final fail in [true, false]) {
    test(
      'genuinely late ${fail ? '401' : 'success'} cannot affect replacement session',
      () async {
        final completion = Completer<AuditMutationResult>();
        var logins = 0;
        final scoped = SessionController(
          (origin) => LateMutationApi(
            origin,
            completion,
            () => SessionLease.fromJson(
              leaseJson(token: logins++ == 0 ? tokenA : tokenB),
            ),
            () => AuthenticatedUser.fromJson({
              ...userJson(role: 'ADMIN'),
              'id': 7 + logins,
            }),
          ),
          clock: () => now,
        )..setOrigin(ApiOrigin.parse('https://example.com'));
        addTearDown(scoped.dispose);
        await scoped.signIn('first', 'password');
        final old = expectLater(
          scoped.createAudit(attempt()),
          throwsA(mutationFailure),
        );
        await tick();
        await scoped.signOut();
        await scoped.signIn('second', 'password');
        if (fail) {
          completion.completeError(ApiFailure.fromStatus(401));
        } else {
          completion.complete(
            AuditMutationResult(
              AuditRecord.fromJson(auditJson()),
              replayed: false,
            ),
          );
        }
        await old;
        expect(scoped.user!.id, 9);
        expect(scoped.mutations.state.phase, AuditMutationPhase.idle);
      },
    );
  }
  test('logout listener during sending cannot let old preflight overwrite session notice', () async {
    Future<void>? logout;
    String? notice;
    void changed() {
      if (session.mutations.busy && logout == null) {
        logout = session.signOut();
        notice = session.notice;
      }
    }

    session.mutations.addListener(changed);
    await expectLater(session.createAudit(attempt()), throwsA(mutationFailure));
    await logout;
    expect(session.notice, notice);
    expect(requests.where((r) => r.url.path == '/audits'), isEmpty);
    session.mutations.removeListener(changed);
  });
  test('superseded review cannot replace new confirmed state', () async {
    final first = Completer<AuditRecord>();
    final second = Completer<AuditRecord>();
    var reads = 0;
    final controller = AuditMutationController(
      authenticated: () => true,
      create: (_) async => AuditMutationResult(
        AuditRecord.fromJson(auditJson(id: 2)),
        replayed: false,
      ),
      update: (_, _, _) async => throw const AuditMutationFailure(
        ApiFailure.timeout,
        unconfirmed: true,
      ),
      delete: (_, _) async {},
      review: (_, _) => reads++ == 0 ? first.future : second.future,
    );
    addTearDown(controller.dispose);
    await expectLater(
      controller.update(1, '"3"', AuditPatch.fromJson({'remarks': 'x'})),
      throwsA(mutationFailure),
    );
    final stale = expectLater(
      controller.reviewLatest(),
      throwsA(mutationFailure),
    );
    final current = controller.reviewLatest();
    second.complete(
      AuditRecord.fromJson({...auditJson(), 'version': 4}, etag: '"4"'),
    );
    await current;
    controller.acknowledgeReview();
    await controller.create(attempt());
    first.complete(AuditRecord.fromJson(auditJson()));
    await stale;
    expect(controller.state.phase, AuditMutationPhase.confirmed);
    expect(controller.state.record!.id, 2);
  });
  test(
    'history scope requires authenticated ADMIN for archived access',
    () async {
      handler = (r) => r.url.path == '/auth/me'
          ? jsonResponse(userJson())
          : jsonResponse({'items': [], 'total': 0, 'page': 1, 'page_size': 10});
      expect(
        (await session.fetchAuditHistory(1, includeDeleted: true)).items,
        isEmpty,
      );
      expect(requests.last.url.queryParameters['include_deleted'], 'true');
      await session.signOut();
      await session.signIn('auditor', 'password');
      final before = requests.length;
      await expectLater(
        session.fetchAuditHistory(1, includeDeleted: true),
        throwsA(isA<ApiFailure>().having((e) => e.status, 'forbidden', 403)),
      );
      expect(requests.length, before);
    },
  );
  test(
    'completed write waits for concurrent resume before publishing result',
    () async {
      final write = Completer<http.StreamedResponse>();
      final identity = Completer<http.StreamedResponse>();
      handler = (r) =>
          r.url.path == '/auth/me' ? identity.future : write.future;
      var published = false;
      final save = session.createAudit(attempt()).then((value) {
        published = true;
        return value;
      });
      await tick();
      final resume = session.verifyOnResume();
      await tick();
      write.complete(
        jsonResponse(auditJson(), status: 201, headers: {'etag': '"3"'}),
      );
      await tick();
      expect(published, false);
      expect(session.mutations.busy, true);
      identity.complete(jsonResponse(userJson(role: 'ADMIN')));
      await resume;
      await save;
      expect(published, true);
    },
  );
  test(
    'cancellation before dispatch prevents a save after resume completes',
    () async {
      final identity = Completer<http.StreamedResponse>();
      handler = (r) => r.url.path == '/auth/me'
          ? identity.future
          : jsonResponse(auditJson(), status: 201, headers: {'etag': '"3"'});
      final resume = session.verifyOnResume();
      await tick();
      final save = expectLater(
        session.createAudit(attempt()),
        throwsA(mutationFailure),
      );
      await tick();
      session.cancelAuditMutation();
      identity.complete(jsonResponse(userJson(role: 'ADMIN')));
      await resume;
      await save;
      expect(requests.where((r) => r.url.path == '/audits'), isEmpty);
    },
  );
  test('confirmed listener logout suppresses the returned protected mutation record', () async {
    handler = (_) =>
        jsonResponse(auditJson(), status: 201, headers: {'etag': '"3"'});
    Future<void>? logout;
    void changed() {
      if (session.mutations.state.phase == AuditMutationPhase.confirmed) {
        logout = session.signOut();
      }
    }

    session.mutations.addListener(changed);
    await expectLater(session.createAudit(attempt()), throwsA(mutationFailure));
    await logout;
    expect(session.user, isNull);
    expect(session.mutations.state.record, isNull);
    session.mutations.removeListener(changed);
  });
  test(
    'review listener logout suppresses the returned protected latest record',
    () async {
      handler = (r) => r.method == 'PATCH'
          ? throw ApiFailure.timeout
          : jsonResponse(
              {...auditJson(), 'version': 4},
              headers: {'etag': '"4"'},
            );
      await expectLater(
        session.updateAudit(1, '"3"', AuditPatch.fromJson({'remarks': 'x'})),
        throwsA(mutationFailure),
      );
      Future<void>? logout;
      void changed() {
        if (session.mutations.state.latest != null) {
          logout = session.signOut();
        }
      }

      session.mutations.addListener(changed);
      await expectLater(session.reviewMutation(), throwsA(mutationFailure));
      await logout;
      expect(session.user, isNull);
      expect(session.mutations.state.latest, isNull);
      session.mutations.removeListener(changed);
    },
  );
  test(
    'resume started immediately after save is checked before dispatch',
    () async {
      final identity = Completer<http.StreamedResponse>();
      handler = (r) => r.url.path == '/auth/me'
          ? identity.future
          : jsonResponse(auditJson(), status: 201, headers: {'etag': '"3"'});
      final save = session.createAudit(attempt());
      final resume = session.verifyOnResume();
      await tick();
      final earlyWrites = requests
          .where((r) => r.url.path == '/audits')
          .toList();
      identity.complete(jsonResponse(userJson(role: 'ADMIN')));
      await resume;
      await save;
      expect(earlyWrites, isEmpty);
    },
  );
  for (final status in [200, 202, 302, 307, 408, 500]) {
    test(
      'post-dispatch HTTP $status is unconfirmed and requires review',
      () async {
        handler = (_) => jsonResponse({}, status: status);
        await expectLater(
          status == 200
              ? session.deleteAudit(1, '"3"')
              : session.updateAudit(
                  1,
                  '"3"',
                  AuditPatch.fromJson({'remarks': 'x'}),
                ),
          throwsA(
            isA<AuditMutationFailure>().having(
              (e) => e.unconfirmed,
              'unconfirmed',
              true,
            ),
          ),
        );
        expect(session.mutations.state.phase, AuditMutationPhase.unknown);
        await expectLater(
          session.deleteAudit(1, '"3"'),
          throwsA(mutationFailure),
        );
        expect(
          requests
              .where((r) => r.method == 'PATCH' || r.method == 'DELETE')
              .length,
          1,
        );
      },
    );
  }
  for (final status in [403, 412, 428, 422]) {
    test('HTTP $status remains typed without raw errors', () async {
      handler = (_) => jsonResponse({'secret': 'never render'}, status: status);
      await expectLater(
        session.updateAudit(1, '"3"', AuditPatch.fromJson({'remarks': 'x'})),
        throwsA(mutationFailure),
      );
      expect(session.mutations.state.failure!.status, status);
      expect(
        session.mutations.state.failure.toString(),
        isNot(contains('never render')),
      );
    });
  }
}
