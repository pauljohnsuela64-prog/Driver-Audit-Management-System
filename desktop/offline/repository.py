"""A thread-owned SQLite store; each public operation has one transaction.

Version 2 is created for empty databases; owned v1 files migrate atomically. Existing files are never reset.
The Windows identity deliberately does not promise raw Android DB interchange.
"""
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import sqlite3
import threading

from .models import (
    AuditFilter, FIELDS, LocalAudit, LocalEvent, LocalPage, LocalProfile,
    OfflineError, invalid_input, new_uuid, normalize_name, normalize_text,
    normalize_values, valid_date, validate_uuid,
)


from .schema import V2 as _SCHEMA, owned, indexes, migrate

_APP_ID = "com.bhli.audit.offline.windows"
_SORTS = {"created": "seq ASC", "-created": "seq DESC", "audit_date": "audit_date ASC, seq ASC", "-audit_date": "audit_date DESC, seq DESC"}


def _schema_error():
    return OfflineError("schema", "This local database is not supported by this app.")


def _storage_error(error):
    code = getattr(error, "sqlite_errorcode", 0) & 255
    if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        return OfflineError("busy", "Local storage is busy. Please retry.")
    if code == sqlite3.SQLITE_FULL:
        return OfflineError("full", "Local storage is full. Free disk space and retry.")
    if code in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
        return OfflineError("corrupt", "The local database could not be read. Keep the file for recovery.")
    return OfflineError("storage", "Local storage could not complete the operation. Please retry.")


def _paging(page, size):
    if type(page) is not int or type(size) is not int or not 1 <= page <= 10000 or not 1 <= size <= 101:
        invalid_input()


def _values(audit):
    return {field: getattr(audit, field) for field in FIELDS}


def _snapshot(audit):
    result = asdict(audit)
    for field in ("created_at", "updated_at", "archived_at"):
        value = result[field]
        result[field] = value.isoformat() if value is not None else None
    return result


def _timestamp(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("Missing timezone")
    return stamp.astimezone(timezone.utc)


def _audit(row):
    try:
        values = normalize_values({field: row[field] for field in FIELDS})
        validate_uuid(row["id"])
        validate_uuid(row["profile_id"])
        if type(row["revision"]) is not int or row["revision"] < 1:
            raise ValueError("Invalid revision")
        return LocalAudit(
            id=row["id"], **values, audited_by_name=normalize_name(row["audited_by_name"]),
            profile_id=row["profile_id"], revision=row["revision"],
            created_at=_timestamp(row["created_at"]), updated_at=_timestamp(row["updated_at"]),
            archived_at=None if row["archived_at"] is None else _timestamp(row["archived_at"]),
        )
    except (KeyError, IndexError, ValueError, TypeError, OfflineError):
        raise OfflineError("corrupt", "The local audit data could not be read. Keep the file for recovery.") from None


class SqliteRepository:
    def __init__(self, path, timeout=.25):
        self._owner = threading.get_ident()
        self._closed = False
        self._connection = None
        try:
            self._connection = sqlite3.connect(path, timeout=timeout, isolation_level=None)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            with self._transaction(write=True):
                self._initialize()
        except BaseException as error:
            if self._connection is not None:
                self._connection.close()
            if isinstance(error, sqlite3.Error):
                raise _storage_error(error) from None
            raise

    def _check(self):
        if threading.get_ident() != self._owner:
            raise OfflineError("thread", "Local storage must be used on its owning thread.")
        if self._closed:
            raise OfflineError("closed", "Local storage is closed.")

    @contextmanager
    def _transaction(self, *, write=False):
        self._check()
        try:
            self._connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield
            self._connection.commit()
        except BaseException as error:
            # SQLite can roll back automatically on FULL. Only roll back a
            # remaining transaction, including one whose COMMIT failed.
            if self._connection.in_transaction:
                self._connection.rollback()
            if isinstance(error, sqlite3.Error):
                raise _storage_error(error) from None
            raise

    def _initialize(self):
        db = self._connection
        version = db.execute("PRAGMA user_version").fetchone()[0]
        tables = {row["name"]: row["sql"] for row in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*'")}
        if db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('view','trigger') LIMIT 1").fetchone() is not None:
            raise _schema_error()
        if version == 0 and not tables:
            for sql in _SCHEMA.values():
                db.execute(sql)
            indexes(db)
            db.executemany("INSERT INTO app_meta (key,value) VALUES (?,?)", (("app_id", _APP_ID), ("installation_id", new_uuid())))
            db.execute("PRAGMA user_version=2")
            return
        if version not in (1, 2):
            raise _schema_error()
        # The v1 schema is owned by this app. Check its complete definition,
        # including constraints, rather than accepting same-named weak tables.
        if not owned(db, version):
            raise _schema_error()
        try:
            meta = dict(db.execute("SELECT key,value FROM app_meta"))
            if meta.get("app_id") != _APP_ID:
                raise _schema_error()
            validate_uuid(meta.get("installation_id"))
            if list(db.execute("PRAGMA foreign_key_check")):
                raise _schema_error()
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise OfflineError("corrupt", "The local database could not be read. Keep the file for recovery.")
        except OfflineError as error:
            if error.code == "validation":
                raise _schema_error() from None
            raise

        if version == 1:
            migrate(db, _audit, _snapshot, _timestamp)

    def _profile(self):
        row = self._connection.execute("SELECT id,name FROM local_profile WHERE singleton=1").fetchone()
        if row is None:
            return None
        try:
            validate_uuid(row["id"])
            name = normalize_name(row["name"])
        except OfflineError:
            raise OfflineError("corrupt", "The local auditor profile could not be read. Keep the file for recovery.") from None
        return LocalProfile(row["id"], name)

    def profile(self):
        with self._transaction():
            return self._profile()

    def save_profile(self, name):
        with self._transaction(write=True):
            name = normalize_name(name)
            previous = self._profile()
            profile = LocalProfile(previous.id if previous else new_uuid(), name)
            self._connection.execute("INSERT OR IGNORE INTO auditor_identities(id) VALUES (?)", (profile.id,))
            self._connection.execute("INSERT INTO local_profile(singleton,id,name) VALUES (1,?,?) ON CONFLICT(singleton) DO UPDATE SET name=excluded.name", (profile.id, profile.name))
            return profile

    def _read(self, record_id):
        row = self._connection.execute("SELECT * FROM audit_records WHERE id=?", (record_id,)).fetchone()
        if row is None:
            raise OfflineError("not_found", "This audit could not be found.")
        return _audit(row)

    def read(self, id):
        with self._transaction():
            validate_uuid(id)
            return self._read(id)

    def list(self, filter):
        with self._transaction():
            if not isinstance(filter, AuditFilter):
                invalid_input()
            _paging(filter.page, filter.page_size)
            if not isinstance(filter.sort, str) or filter.sort not in _SORTS or type(filter.include_archived) is not bool:
                invalid_input()
            if any(value is not None and not valid_date(value) for value in (filter.date_from, filter.date_to)):
                invalid_input()
            if filter.date_from is not None and filter.date_to is not None and filter.date_from > filter.date_to:
                invalid_input()
            clauses = [] if filter.include_archived else ["archived_at IS NULL"]
            args = []
            for field, value in (("driver_name", filter.driver), ("plate_number", filter.plate), ("station", filter.station)):
                text = normalize_text(value, 200, optional=True)
                if text:
                    clauses.append(f"{field} LIKE ? ESCAPE '\\'")
                    args.append("%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
            for operator, value in ((">=", filter.date_from), ("<=", filter.date_to)):
                if value is not None:
                    clauses.append(f"audit_date {operator} ?")
                    args.append(value)
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            total = self._connection.execute("SELECT count(*) FROM audit_records" + where, args).fetchone()[0]
            rows = self._connection.execute("SELECT * FROM audit_records" + where + " ORDER BY " + _SORTS[filter.sort] + " LIMIT ? OFFSET ?", (*args, filter.page_size, (filter.page - 1) * filter.page_size))
            return LocalPage(tuple(_audit(row) for row in rows), total, filter.page, filter.page_size)

    def _actor(self):
        actor = self._profile()
        if actor is None:
            raise OfflineError("profile_required", "Enter your local auditor name first.")
        return actor

    def _event(self, action, actor, after, before):
        self._connection.execute("INSERT INTO audit_events (id,audit_id,revision,action,actor_name,actor_profile_id,created_at,before_json,after_json) VALUES (?,?,?,?,?,?,?,?,?)", (new_uuid(), after.id, after.revision, action, actor.name, actor.id, after.updated_at.isoformat(), None if before is None else json.dumps(_snapshot(before)), json.dumps(_snapshot(after))))

    def create(self, id, values):
        with self._transaction(write=True):
            validate_uuid(id)
            values = normalize_values(values)
            row = self._connection.execute("SELECT * FROM audit_records WHERE id=?", (id,)).fetchone()
            if row is not None:
                current = _audit(row)
                original = self._connection.execute("SELECT after_json FROM audit_events WHERE audit_id=? AND action='CREATE'", (id,)).fetchall()
                if not current.archived and len(original) == 1:
                    try:
                        original_values = _values(_audit(json.loads(original[0]["after_json"])))
                    except (ValueError, TypeError):
                        raise OfflineError("corrupt", "The local audit history could not be read.") from None
                    if original_values == values:
                        return current
                raise OfflineError("conflict", "This audit identifier already has different content.")
            actor = self._actor()
            now = datetime.now(timezone.utc)
            audit = LocalAudit(id, **values, audited_by_name=actor.name, profile_id=actor.id, revision=1, created_at=now, updated_at=now)
            snapshot = _snapshot(audit)
            columns = tuple(snapshot)
            self._connection.execute("INSERT INTO audit_records (" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")", tuple(snapshot.values()))
            self._event("CREATE", actor, audit, None)
            return audit

    def _change(self, record_id, expected_revision, values, *, archive=False):
        with self._transaction(write=True):
            validate_uuid(record_id)
            if type(expected_revision) is not int or expected_revision < 1:
                invalid_input()
            normalized = None if archive else normalize_values(values)
            before = self._read(record_id)
            if before.revision != expected_revision or before.archived:
                raise OfflineError("conflict", "This audit has changed. Reload it before trying again.")
            if not archive and _values(before) == normalized:
                return before
            actor = self._actor()
            now = datetime.now(timezone.utc)
            after = replace(before, **(_values(before) if archive else normalized), revision=expected_revision + 1, updated_at=now, archived_at=now if archive else None)
            snapshot = _snapshot(after)
            changed = self._connection.execute("UPDATE audit_records SET " + ",".join(column + "=?" for column in snapshot) + " WHERE id=? AND revision=? AND archived_at IS NULL", (*snapshot.values(), record_id, expected_revision))
            if changed.rowcount != 1:
                raise OfflineError("conflict", "This audit has changed. Reload it before trying again.")
            self._event("ARCHIVE" if archive else "UPDATE", actor, after, before)
            return after

    def update(self, id, expected_revision, values):
        return self._change(id, expected_revision, values)

    def archive(self, id, expected_revision):
        return self._change(id, expected_revision, None, archive=True)

    def history(self, id, page=1, page_size=25):
        with self._transaction():
            validate_uuid(id)
            _paging(page, page_size)
            self._read(id)
            total = self._connection.execute("SELECT count(*) FROM audit_events WHERE audit_id=?", (id,)).fetchone()[0]
            rows = self._connection.execute("SELECT * FROM audit_events WHERE audit_id=? ORDER BY revision DESC LIMIT ? OFFSET ?", (id, page_size, (page - 1) * page_size))
            events = []
            try:
                for row in rows:
                    events.append(LocalEvent(row["id"], row["audit_id"], row["revision"], row["action"], row["actor_name"], row["actor_profile_id"], _timestamp(row["created_at"]), None if row["before_json"] is None else _audit(json.loads(row["before_json"])), _audit(json.loads(row["after_json"]))))
            except (ValueError, TypeError, KeyError):
                raise OfflineError("corrupt", "The local audit history could not be read.") from None
            return LocalPage(tuple(events), total, page, page_size)

    def close(self):
        if threading.get_ident() != self._owner:
            raise OfflineError("thread", "Local storage must be used on its owning thread.")
        if self._closed:
            return
        try:
            self._connection.close()
            self._closed = True
        except sqlite3.Error as error:
            raise _storage_error(error) from None
