import 'dart:io';
import 'dart:typed_data';

import 'package:bhli_audit/offline/models.dart';
import 'package:bhli_audit/offline/sqlite_repository.dart';
import 'package:bhli_audit/offline/transfer.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

class TransferFactory extends DatabaseFactory {
  late Database db;
  bool failCommit = false;
  @override
  Future<Database> openDatabase(
    String path, {
    OpenDatabaseOptions? options,
  }) async {
    db = await databaseFactoryFfi.openDatabase(path, options: options);
    return TransferDatabase(this);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class TransferDatabase extends Database {
  TransferDatabase(this.owner);
  final TransferFactory owner;
  @override
  Future<T> transaction<T>(
    Future<T> Function(Transaction) action, {
    bool? exclusive,
  }) => owner.db.transaction((txn) async {
    final result = await action(txn);
    if (owner.failCommit) {
      owner.failCommit = false;
      await txn.execute('CREATE TABLE fault_parent(id INTEGER PRIMARY KEY)');
      await txn.execute(
        'CREATE TABLE fault_child(id INTEGER REFERENCES fault_parent(id) DEFERRABLE INITIALLY DEFERRED)',
      );
      await txn.insert('fault_child', {'id': 9});
    }
    return result;
  }, exclusive: exclusive);
  @override
  Future<void> close() => owner.db.close();
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

AuditValues fields([
  String name = 'Fictional Driver',
  String date = '2026-11-05',
]) => AuditValues(
  driverName: name,
  auditDate: date,
  station: 'North',
  plateNumber: '00047',
);
Matcher fails(String code) =>
    isA<OfflineFailure>().having((e) => e.code, 'code', code);

void main() {
  setUpAll(sqfliteFfiInit);
  late Directory directory;
  late dynamic source, target;
  late TransferFactory factory;
  setUp(() async {
    directory = await Directory.systemTemp.createTemp('bhli-transfer-store-');
    source = await SqliteOfflineRepository.open(
      '${directory.path}/source.db',
      factory: databaseFactoryFfi,
    );
    factory = TransferFactory();
    target = await SqliteOfflineRepository.open(
      '${directory.path}/target.db',
      factory: factory,
    );
    await source.saveProfile('Fictional Sender');
    await target.saveProfile('Fictional Recipient');
  });
  tearDown(() async {
    await source.close();
    await target.close();
    await directory.delete(recursive: true);
  });

  test('independent SQLite profiles exchange archived complete histories in both directions', () async {
    final id = newUuid();
    await source.create(id, fields('Fictional Jos\u00e9 \u{1f69a}'));
    await source.saveProfile('Renamed Sender');
    await source.update(id, 1, fields('Edited Driver'));
    await source.archive(id, 2);
    final local = await target.profile();
    final Uint8List raw = await source.exportTransfer();
    final output = Platform.environment['DAMS_TRANSFER_CROSS_OUTPUT'];
    if (output != null) await File(output).writeAsBytes(raw, flush: true);
    final preview = await target.previewTransfer(raw);
    expect(preview.newIds, [id]);
    final result = await target.applyTransfer(raw, preview);
    expect(result.imported, 1);
    expect((await target.profile()).id, local.id);
    expect((await target.profile()).name, 'Fictional Recipient');
    expect((await target.read(id)).auditedByName, 'Fictional Sender');
    final history = await target.history(id);
    expect(history.map((e) => e.revision).toList(), [3, 2, 1]);
    expect(history.first.actorName, 'Renamed Sender');
    expect(history.last.actorName, 'Fictional Sender');
    final other = newUuid();
    await target.create(other, fields('Return Driver'));
    final Uint8List back = await target.exportTransfer();
    final reverse = await source.previewTransfer(back);
    expect(reverse.newIds, [other]);
    expect(reverse.duplicateIds, [id]);
    await source.applyTransfer(back, reverse);
    expect((await source.read(other)).auditedByName, 'Fictional Recipient');
    await target.saveProfile('Renamed Recipient');
    await target.close();
    target = await SqliteOfflineRepository.open(
      '${directory.path}/target.db',
      factory: factory,
    );
    expect((await target.read(id)).archived, isTrue);
    expect((await target.profile()).name, 'Renamed Recipient');
    expect(await factory.db.rawQuery('PRAGMA foreign_key_check'), isEmpty);
  });

  test(
    'same package reimport is a no-op and local edit becomes conflict',
    () async {
      final id = newUuid();
      await source.create(id, fields());
      final Uint8List raw = await source.exportTransfer();
      await target.applyTransfer(raw, await target.previewTransfer(raw));
      final duplicate = await target.previewTransfer(raw);
      expect(duplicate.duplicateIds, [id]);
      expect((await target.applyTransfer(raw, duplicate)).imported, 0);
      await target.update(id, 1, fields('Local edit'));
      final conflict = await target.previewTransfer(raw);
      expect(conflict.conflictIds, [id]);
      expect((await target.applyTransfer(raw, conflict)).conflicts, 1);
      expect((await target.read(id)).values.driverName, 'Local edit');
      expect((await factory.db.query('transfer_receipts')).length, 1);
    },
  );

  test('preview race aborts before receipt or registry changes', () async {
    final id = newUuid();
    await source.create(id, fields());
    final Uint8List raw = await source.exportTransfer();
    final preview = await target.previewTransfer(raw);
    await target.create(id, fields('Concurrent local'));
    final before = await factory.db.query('auditor_identities');
    await expectLater(
      target.applyTransfer(raw, preview),
      throwsA(fails('conflict')),
    );
    expect(await factory.db.query('transfer_receipts'), isEmpty);
    expect(await factory.db.query('auditor_identities'), before);
    expect((await target.read(id)).values.driverName, 'Concurrent local');
  });

  test('history UUID collision rejects whole package', () async {
    final sourceId = newUuid(), localId = newUuid();
    await source.create(sourceId, fields());
    await target.create(localId, fields());
    final package = decodeTransfer(await source.exportTransfer());
    final collision = (await target.history(localId)).single.id;
    package.events.single['id'] = collision;
    final raw = encodeTransfer(
      package.manifest,
      package.audits,
      package.events,
    );
    await expectLater(target.previewTransfer(raw), throwsA(fails('conflict')));
    expect((await target.list(const AuditFilter())).total, 1);
    expect(await factory.db.query('transfer_receipts'), isEmpty);
  });

  test('package UUID reuse with changed manifest conflicts', () async {
    await source.create(newUuid(), fields());
    final Uint8List raw = await source.exportTransfer();
    await target.applyTransfer(raw, await target.previewTransfer(raw));
    final package = decodeTransfer(raw);
    package.manifest['exported_at'] = '2026-11-05T00:00:00.000000Z';
    final changed = encodeTransfer(
      package.manifest,
      package.audits,
      package.events,
    );
    await expectLater(
      target.previewTransfer(changed),
      throwsA(fails('conflict')),
    );
    expect((await factory.db.query('transfer_receipts')).length, 1);
  });

  for (final failure in ['receipt', 'commit']) {
    test(
      '$failure failure rolls back identities records events and receipt',
      () async {
        await source.create(newUuid(), fields());
        final Uint8List raw = await source.exportTransfer();
        final preview = await target.previewTransfer(raw);
        final registry = await factory.db.query('auditor_identities');
        if (failure == 'receipt') {
          await factory.db.execute(
            "CREATE TRIGGER fail_receipt BEFORE INSERT ON transfer_receipts BEGIN SELECT RAISE(ABORT, 'private fault'); END",
          );
        } else {
          factory.failCommit = true;
        }
        await expectLater(
          target.applyTransfer(raw, preview),
          throwsA(fails('storage')),
        );
        expect(await factory.db.query('auditor_identities'), registry);
        expect(await factory.db.query('audit_records'), isEmpty);
        expect(await factory.db.query('audit_events'), isEmpty);
        expect(await factory.db.query('transfer_receipts'), isEmpty);
        expect((await target.profile()).name, 'Fictional Recipient');
      },
    );
  }

  test(
    'date filters include archived records and empty export is valid',
    () async {
      final id = newUuid();
      await source.create(id, fields());
      await source.archive(id, 1);
      await source.create(newUuid(), fields('Other date', '2026-10-01'));
      final filtered = decodeTransfer(
        await source.exportTransfer(
          dateFrom: '2026-11-05',
          dateTo: '2026-11-05',
        ),
      );
      expect(filtered.audits.single['id'], id);
      expect(filtered.events.length, 2);
      expect(
        decodeTransfer(await source.exportTransfer(dateFrom: '2026-12-01'))
            .audits,
        isEmpty,
      );
      await expectLater(
        source.exportTransfer(dateFrom: '2026-12-01', dateTo: '2026-01-01'),
        throwsA(fails('validation')),
      );
    },
  );

  test('cancellation and malformed package preserve empty recipient', () async {
    await source.create(newUuid(), fields());
    final Uint8List raw = await source.exportTransfer();
    final preview = await target.previewTransfer(raw);
    await expectLater(
      target.applyTransfer(raw, preview, cancel: () => true),
      throwsA(fails('canceled')),
    );
    await expectLater(
      target.previewTransfer(Uint8List.fromList([1, 2, 3])),
      throwsA(fails('validation')),
    );
    expect(await factory.db.query('audit_records'), isEmpty);
    expect(await factory.db.query('transfer_receipts'), isEmpty);
  });

  test(
    'admission freezes caller bytes before queued preview and apply',
    () async {
      final id = newUuid();
      await source.create(id, fields());
      final Uint8List original = await source.exportTransfer();
      final mutable = Uint8List.fromList(original);
      final pending = target.previewTransfer(mutable);
      mutable.fillRange(0, mutable.length, 0);
      final preview = await pending;
      expect(preview.newIds, [id]);
      final applying = Uint8List.fromList(original);
      final result = target.applyTransfer(applying, preview);
      applying.fillRange(0, applying.length, 0);
      expect((await result).imported, 1);
      expect((await target.read(id)).values.plateNumber, '00047');
    },
  );

  final pythonInput = Platform.environment['DAMS_TRANSFER_CROSS_INPUT'];
  if (pythonInput != null) {
    test('actual Python SQLite package imports with unchanged complete wire history', () async {
      final raw = await File(pythonInput).readAsBytes();
      final package = decodeTransfer(raw);
      final local = await target.profile();
      final preview = await target.previewTransfer(raw);
      expect(preview.newIds.length, package.audits.length);
      expect(
        (await target.applyTransfer(raw, preview)).imported,
        package.audits.length,
      );
      final result = decodeTransfer(await target.exportTransfer());
      expect(canonicalJson(result.audits), canonicalJson(package.audits));
      expect(canonicalJson(result.events), canonicalJson(package.events));
      expect((await target.profile()).id, local.id);
      expect((await target.profile()).name, local.name);
      expect(
        (await target.previewTransfer(raw)).duplicateIds.length,
        package.audits.length,
      );
    });
  }
}
