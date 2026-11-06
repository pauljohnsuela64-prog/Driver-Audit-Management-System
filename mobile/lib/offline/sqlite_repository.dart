import 'dart:convert';
import 'dart:typed_data';

import 'package:sqflite/sqflite.dart';

import 'models.dart';
import 'repository.dart';
import 'reporting.dart';
import 'schema.dart';
import 'transfer_store.dart';

/// One admitted-operation queue owns this connection, including shutdown.
class SqliteOfflineRepository
    implements
        OfflineRepository,
        OfflineTransferRepository,
        OfflineReportingRepository {
  SqliteOfflineRepository._(this._db);
  final Database _db;
  Future<void> _tail = Future.value();
  Future<void>? _closing;
  bool _accepting = true;
  static const _appId = 'com.bhli.audit.offline';
  static const _schemaFailure = OfflineFailure(
    'schema',
    'This local database is not supported by this app.',
  );
  static const _storageFailure = OfflineFailure(
    'storage',
    'Local storage could not complete the operation. Please retry.',
  );

  static Future<SqliteOfflineRepository> open(
    String path, {
    DatabaseFactory? factory,
  }) async {
    Database? db;
    try {
      db = await (factory ?? databaseFactory).openDatabase(
        path,
        options: OpenDatabaseOptions(
          singleInstance: false,
          onConfigure: (db) async {
            await db.execute('PRAGMA foreign_keys = ON');
          },
        ),
      );
      await db.transaction((txn) async {
        final version =
            (await txn.rawQuery('PRAGMA user_version')).first.values.first
                as int;
        final tables = await txn.rawQuery(
          // Android creates android_metadata before application schema setup.
          // It is platform-owned, not a fifth application table.
          "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' AND name != 'android_metadata'",
        );
        if (version == 0 && tables.isEmpty) {
          final objects = await txn.rawQuery(
            "SELECT name FROM sqlite_master WHERE name NOT GLOB 'sqlite_*' AND name != 'android_metadata'",
          );
          if (objects.isNotEmpty) throw _schemaFailure;
          for (final sql in offlineV2Tables.values) {
            await txn.execute(sql);
          }
          await createOfflineIndexes(txn);
          await txn.insert('app_meta', {'key': 'app_id', 'value': _appId});
          await txn.insert('app_meta', {
            'key': 'installation_id',
            'value': newUuid(),
          });
          await verifyOfflineSchema(txn, 2);
          await txn.execute('PRAGMA user_version = 2');
        } else {
          if (version != 1 && version != 2) throw _schemaFailure;
          await verifyOfflineSchema(txn, version);
          final identities = await validateOfflineRows(txn, version);
          if (version == 1) await migrateOfflineV1(txn, identities);
        }
      });
      return SqliteOfflineRepository._(db);
    } catch (error) {
      await db?.close();
      if (error is OfflineFailure) rethrow;
      throw _storageFailure;
    }
  }

  Future<T> _run<T>(Future<T> Function(Transaction txn) work) {
    if (!_accepting) {
      return Future.error(
        const OfflineFailure('closed', 'Local storage is closed.'),
      );
    }
    final result = _tail.then((_) async {
      try {
        return await _db.transaction(work);
      } on OfflineFailure {
        rethrow;
      } catch (_) {
        throw _storageFailure;
      }
    });
    _tail = result.then<void>((_) {}, onError: (Object _, StackTrace _) {});
    return result;
  }

  @override
  Future<Uint8List> exportTransfer({
    String? dateFrom,
    String? dateTo,
    bool Function()? cancel,
  }) => _run(
    (txn) => exportTransferTransaction(
      txn,
      dateFrom: dateFrom,
      dateTo: dateTo,
      cancel: cancel,
    ),
  );

  @override
  Future<ImportPreview> previewTransfer(Uint8List raw) {
    final frozen = freezeTransferBytes(raw);
    return _run((txn) => previewTransferTransaction(txn, frozen));
  }

  @override
  Future<ImportResult> applyTransfer(
    Uint8List raw,
    ImportPreview preview, {
    bool Function()? cancel,
  }) {
    final frozen = freezeTransferBytes(raw);
    return _run(
      (txn) => applyTransferTransaction(txn, frozen, preview, cancel: cancel),
    );
  }

  @override
  Future<OfflineReportSnapshot> reportSnapshot(
    AuditFilter filter, {
    bool includeRows = false,
    bool Function()? cancel,
  }) => _run(
    (txn) => reportSnapshotTransaction(
      txn,
      filter,
      includeRows: includeRows,
      cancel: cancel,
    ),
  );

  static void _id(String id) {
    if (!validOfflineUuid(id)) invalidInput();
  }

  static void _paging(int page, int size) {
    if (page < 1 || page > 10000 || size < 1 || size > 101) invalidInput();
  }

  static LocalAudit _audit(Map<String, Object?> row) => LocalAudit(
    id: row['id'] as String,
    values: _values(row),
    auditedByName: row['audited_by_name'] as String,
    profileId: row['profile_id'] as String,
    createdAt: DateTime.parse(row['created_at'] as String).toUtc(),
    updatedAt: DateTime.parse(row['updated_at'] as String).toUtc(),
    revision: row['revision'] as int,
    archivedAt: row['archived_at'] == null
        ? null
        : DateTime.parse(row['archived_at'] as String).toUtc(),
  );
  static AuditValues _values(Map<String, Object?> row) => AuditValues.fromJson({
    for (final key in [
      'driver_name',
      'helper_name',
      'audit_date',
      'station',
      'plate_number',
      'remarks',
    ])
      key: row[key],
  });
  static Map<String, Object?> _snapshot(LocalAudit audit) => {
    'id': audit.id,
    ...audit.values.toJson(),
    'audited_by_name': audit.auditedByName,
    'profile_id': audit.profileId,
    'revision': audit.revision,
    'created_at': audit.createdAt.toIso8601String(),
    'updated_at': audit.updatedAt.toIso8601String(),
    'archived_at': audit.archivedAt?.toIso8601String(),
  };
  static Future<LocalProfile?> _profile(Transaction txn) async {
    final rows = await txn.query('local_profile', where: 'singleton = 1');
    return rows.isEmpty
        ? null
        : LocalProfile(
            id: rows.single['id'] as String,
            name: rows.single['name'] as String,
          );
  }

  static Future<LocalAudit> _read(Transaction txn, String id) async {
    final rows = await txn.query(
      'audit_records',
      where: 'id = ?',
      whereArgs: [id],
    );
    if (rows.isEmpty) {
      throw const OfflineFailure('not_found', 'This audit could not be found.');
    }
    return _audit(rows.single);
  }

  @override
  Future<LocalProfile?> profile() => _run(_profile);
  @override
  Future<LocalProfile> saveProfile(String name) => _run((txn) async {
    final normalized = offlineText(name, 200);
    final previous = await _profile(txn);
    final profile = LocalProfile(
      id: previous?.id ?? newUuid(),
      name: normalized,
    );
    if (previous == null) {
      await txn.insert('auditor_identities', {'id': profile.id});
      await txn.insert('local_profile', {
        'singleton': 1,
        'id': profile.id,
        'name': profile.name,
      });
    } else {
      await txn.update('local_profile', {
        'name': profile.name,
      }, where: 'singleton = 1');
    }
    return profile;
  });
  @override
  Future<LocalAudit> read(String id) => _run((txn) {
    _id(id);
    return _read(txn, id);
  });
  @override
  Future<AuditPage> list(AuditFilter filter) => _run((txn) async {
    _paging(filter.page, filter.pageSize);
    if (!{
          'created',
          '-created',
          'audit_date',
          '-audit_date',
        }.contains(filter.sort) ||
        (filter.dateFrom != null && !validOfflineDate(filter.dateFrom!)) ||
        (filter.dateTo != null && !validOfflineDate(filter.dateTo!)) ||
        (filter.dateFrom != null &&
            filter.dateTo != null &&
            filter.dateFrom!.compareTo(filter.dateTo!) > 0)) {
      invalidInput();
    }
    final clauses = <String>[];
    final args = <Object?>[];
    if (!filter.includeArchived) clauses.add('archived_at IS NULL');
    for (final entry in {
      'driver_name': filter.driver,
      'plate_number': filter.plate,
      'station': filter.station,
    }.entries) {
      final text = offlineText(entry.value, 200, optional: true);
      if (text.isNotEmpty) {
        clauses.add("${entry.key} LIKE ? ESCAPE '\\'");
        args.add(
          '%${text.replaceAll('\\', '\\\\').replaceAll('%', '\\%').replaceAll('_', '\\_')}%',
        );
      }
    }
    if (filter.dateFrom != null) {
      clauses.add('audit_date >= ?');
      args.add(filter.dateFrom);
    }
    if (filter.dateTo != null) {
      clauses.add('audit_date <= ?');
      args.add(filter.dateTo);
    }
    final where = clauses.isEmpty ? null : clauses.join(' AND ');
    final count = await txn.query(
      'audit_records',
      columns: ['COUNT(*) AS total'],
      where: where,
      whereArgs: args,
    );
    final order = switch (filter.sort) {
      'created' => 'seq ASC',
      '-created' => 'seq DESC',
      'audit_date' => 'audit_date ASC, seq ASC',
      _ => 'audit_date DESC, seq DESC',
    };
    final rows = await txn.query(
      'audit_records',
      where: where,
      whereArgs: args,
      orderBy: order,
      limit: filter.pageSize,
      offset: (filter.page - 1) * filter.pageSize,
    );
    return AuditPage(
      items: rows.map(_audit).toList(),
      total: count.single['total'] as int,
      page: filter.page,
      pageSize: filter.pageSize,
    );
  });

  static Future<void> _event(
    Transaction txn,
    String action,
    LocalProfile actor,
    LocalAudit after,
    LocalAudit? before,
  ) => txn
      .insert('audit_events', {
        'id': newUuid(),
        'audit_id': after.id,
        'revision': after.revision,
        'action': action,
        'actor_name': actor.name,
        'actor_profile_id': actor.id,
        'created_at': after.updatedAt.toIso8601String(),
        'before_json': before == null ? null : jsonEncode(_snapshot(before)),
        'after_json': jsonEncode(_snapshot(after)),
      })
      .then((_) {});

  @override
  Future<LocalAudit> create(String id, AuditValues values) => _run((txn) async {
    _id(id);
    final existing = await txn.query(
      'audit_records',
      where: 'id = ?',
      whereArgs: [id],
    );
    if (existing.isNotEmpty) {
      final current = _audit(existing.single);
      final original = await txn.query(
        'audit_events',
        where: "audit_id = ? AND action = 'CREATE'",
        whereArgs: [id],
      );
      if (!current.archived && original.length == 1) {
        final snapshot = jsonDecode(
          original.single['after_json'] as String,
        ) as Map<String, dynamic>;
        if (jsonEncode(_values(snapshot).toJson()) ==
            jsonEncode(values.toJson())) {
          return current;
        }
      }
      throw const OfflineFailure(
        'conflict',
        'This audit identifier already has different content.',
      );
    }
    final actor = await _profile(txn);
    if (actor == null) {
      throw const OfflineFailure(
        'profile_required',
        'Enter your local auditor name first.',
      );
    }
    final now = DateTime.now().toUtc();
    final audit = LocalAudit(
      id: id,
      values: values,
      auditedByName: actor.name,
      profileId: actor.id,
      createdAt: now,
      updatedAt: now,
      revision: 1,
    );
    await txn.insert('audit_records', _snapshot(audit));
    await _event(txn, 'CREATE', actor, audit, null);
    return audit;
  });

  Future<LocalAudit> _change(String id, int revision, AuditValues? values) =>
      _run((txn) async {
        _id(id);
        if (revision < 1) invalidInput();
        final before = await _read(txn, id);
        if (before.revision != revision || before.archived) {
          throw const OfflineFailure(
            'conflict',
            'This audit has changed. Reload it before trying again.',
          );
        }
        if (values != null &&
            jsonEncode(values.toJson()) == jsonEncode(before.values.toJson())) {
          return before;
        }
        final actor = await _profile(txn);
        if (actor == null) {
          throw const OfflineFailure(
            'profile_required',
            'Enter your local auditor name first.',
          );
        }
        final now = DateTime.now().toUtc();
        final after = LocalAudit(
          id: id,
          values: values ?? before.values,
          auditedByName: before.auditedByName,
          profileId: before.profileId,
          createdAt: before.createdAt,
          updatedAt: now,
          revision: revision + 1,
          archivedAt: values == null ? now : null,
        );
        final changed = await txn.update(
          'audit_records',
          _snapshot(after),
          where: 'id = ? AND revision = ? AND archived_at IS NULL',
          whereArgs: [id, revision],
        );
        if (changed != 1) {
          throw const OfflineFailure(
            'conflict',
            'This audit has changed. Reload it before trying again.',
          );
        }
        await _event(
          txn,
          values == null ? 'ARCHIVE' : 'UPDATE',
          actor,
          after,
          before,
        );
        return after;
      });
  @override
  Future<LocalAudit> update(String id, int revision, AuditValues values) =>
      _change(id, revision, values);
  @override
  Future<LocalAudit> archive(String id, int revision) =>
      _change(id, revision, null);
  @override
  Future<List<LocalEvent>> history(
    String id, {
    int page = 1,
    int pageSize = 10,
  }) => _run((txn) async {
    _id(id);
    _paging(page, pageSize);
    await _read(txn, id);
    final rows = await txn.query(
      'audit_events',
      where: 'audit_id = ?',
      whereArgs: [id],
      orderBy: 'revision DESC',
      limit: pageSize,
      offset: (page - 1) * pageSize,
    );
    return List.unmodifiable(
      rows.map(
        (row) => LocalEvent(
          id: row['id'] as String,
          auditId: row['audit_id'] as String,
          revision: row['revision'] as int,
          action: row['action'] as String,
          actorName: row['actor_name'] as String,
          actorProfileId: row['actor_profile_id'] as String,
          createdAt: DateTime.parse(row['created_at'] as String).toUtc(),
          before: row['before_json'] == null
              ? null
              : Map<String, Object?>.from(
                  jsonDecode(row['before_json'] as String) as Map,
                ),
          after: Map<String, Object?>.from(
            jsonDecode(row['after_json'] as String) as Map,
          ),
        ),
      ),
    );
  });
  @override
  Future<void> close() {
    _accepting = false;
    return _closing ??= _tail.then((_) async {
      try {
        await _db.close();
      } catch (_) {
        throw _storageFailure;
      }
    });
  }
}
