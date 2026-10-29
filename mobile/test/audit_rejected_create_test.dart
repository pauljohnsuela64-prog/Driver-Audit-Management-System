import 'package:bhli_audit/core/network/api_failure.dart';
import 'package:bhli_audit/features/audits/audit_draft.dart';
import 'package:bhli_audit/features/audits/audit_mutation_controller.dart';
import 'package:bhli_audit/features/audits/models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  PendingAuditCreate attempt() => PendingAuditCreate(
    AuditDraft(
      driverName: 'Driver',
      auditDate: '2026-10-28',
      station: 'Station',
      plateNumber: '0001',
    ),
  );
  AuditMutationController coordinator(
    Future<AuditMutationResult> Function(PendingAuditCreate) create,
  ) => AuditMutationController(
    authenticated: () => true,
    create: create,
    update: (_, _, _) async => throw StateError('unused'),
    delete: (_, _) async {},
    review: (_, _) async => throw StateError('unused'),
  );
  test(
    'definitive first422 can release rejected attempt for draft corrections',
    () async {
      var calls = 0;
      final c = coordinator((_) async {
        calls++;
        throw AuditMutationFailure(
          ApiFailure.fromStatus(422),
          unconfirmed: false,
        );
      });
      addTearDown(c.dispose);
      final a = attempt();
      await expectLater(c.create(a), throwsA(isA<AuditMutationFailure>()));
      expect(c.canCorrectRejectedCreate, true);
      c.releaseRejectedCreate();
      expect(c.pendingCreate, isNull);
      expect(c.state.phase, AuditMutationPhase.idle);
      expect(calls, 1);
    },
  );
  test(
    'a422 after unknown outcome cannot discard frozen retry information',
    () async {
      var calls = 0;
      final c = coordinator((_) async {
        calls++;
        throw AuditMutationFailure(
          calls == 1 ? ApiFailure.network : ApiFailure.fromStatus(422),
          unconfirmed: calls == 1,
        );
      });
      addTearDown(c.dispose);
      final a = attempt();
      await expectLater(c.create(a), throwsA(isA<AuditMutationFailure>()));
      await expectLater(c.retryCreate(), throwsA(isA<AuditMutationFailure>()));
      expect(c.canCorrectRejectedCreate, false);
      expect(c.releaseRejectedCreate, throwsA(isA<AuditMutationFailure>()));
      expect(c.pendingCreate, same(a));
      expect(calls, 2);
    },
  );
}
