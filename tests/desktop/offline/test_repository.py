"""Real temporary SQLite stores exercise durability and failure atomicity."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import timezone

import pytest

from desktop.offline.models import AuditFilter, LocalAudit, OfflineError, new_uuid
from desktop.offline.repository import SqliteRepository


VALUES = dict(driver_name="Test Driver", helper_name=None, audit_date="2024-02-29", station="Test Station", plate_number="TEST-1", remarks=None)


@pytest.fixture
def repo(tmp_path):
    store = SqliteRepository(tmp_path / "test.db")
    yield store
    store.close()


def error(code, work):
    with pytest.raises(OfflineError) as caught:
        work()
    assert caught.value.code == code
    return caught.value


def seed(repo):
    repo.save_profile("Test Auditor")
    return repo.create(new_uuid(), VALUES)


def test_empty_schema_profile_creation_rename_and_reopen(tmp_path):
    path = tmp_path / "test.db"
    repo = SqliteRepository(path)
    assert repo.profile() is None
    assert repo.list(AuditFilter()).items == ()
    assert repo.list(AuditFilter()).total == 0
    error("profile_required", lambda: repo.create(new_uuid(), VALUES))
    profile = repo.save_profile("  Test Auditor  ")
    audit = repo.create(new_uuid(), VALUES)
    renamed = repo.save_profile("Renamed Auditor")
    assert renamed.id == profile.id
    assert audit.audited_by_name == "Test Auditor"
    assert audit.created_at.tzinfo == timezone.utc
    assert audit.updated_at == audit.created_at
    assert repo.read(audit.id) == audit
    repo.close()
    repo = SqliteRepository(path)
    assert repo.profile() == renamed
    assert repo.read(audit.id) == audit
    assert repo.history(audit.id).items[0].after == audit
    assert repo._connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert repo._connection.execute("SELECT value FROM app_meta WHERE key='app_id'").fetchone()[0] == "com.bhli.audit.offline.windows"
    repo.close()


def test_history_immutable_attribution_noop_edit_and_archive(repo):
    audit = seed(repo)
    assert repo.update(audit.id, 1, VALUES) == audit
    assert repo.history(audit.id).total == 1
    repo.save_profile("Second Auditor")
    changed = repo.update(audit.id, 1, dict(VALUES, remarks="Edited"))
    assert changed.revision == 2 and changed.audited_by_name == "Test Auditor"
    archived = repo.archive(audit.id, 2)
    assert archived.archived_at == archived.updated_at and archived.revision == 3
    assert repo.list(AuditFilter()).total == 0
    assert repo.list(AuditFilter(include_archived=True)).items == (archived,)
    page = repo.history(audit.id, page=1, page_size=2)
    assert page.total == 3 and page.page_size == 2
    assert [e.action for e in page.items] == ["ARCHIVE", "UPDATE"]
    event = page.items[1]
    assert event.actor_name == "Second Auditor"
    assert event.actor_profile_id == audit.profile_id
    assert event.before == audit and event.after == changed
    assert isinstance(event.after, LocalAudit)
    with pytest.raises(FrozenInstanceError):
        event.after.driver_name = "Changed"
    with pytest.raises(FrozenInstanceError):
        event.action = "CREATE"
    assert repo.history(audit.id, page=2, page_size=2).items[0].before is None
    error("conflict", lambda: repo.archive(audit.id, 3))
    error("conflict", lambda: repo.update(audit.id, 3, VALUES))


def test_uuid_replay_compares_original_payload_even_after_edit(repo):
    original = seed(repo)
    assert repo.create(original.id, VALUES) == original
    edited = repo.update(original.id, 1, dict(VALUES, remarks="Changed"))
    repo.save_profile("Renamed")
    assert repo.create(original.id, VALUES) == edited
    error("conflict", lambda: repo.create(original.id, dict(VALUES, remarks="Changed")))
    assert repo.history(original.id).total == 2
    repo.archive(original.id, 2)
    error("conflict", lambda: repo.create(original.id, VALUES))


def test_two_connections_stale_revision_and_busy_rollback(tmp_path):
    path = tmp_path / "test.db"
    first = SqliteRepository(path, timeout=.01)
    audit = seed(first)
    second = SqliteRepository(path, timeout=.01)
    second.update(audit.id, 1, dict(VALUES, station="Other"))
    error("conflict", lambda: first.update(audit.id, 1, VALUES))
    first._connection.execute("BEGIN IMMEDIATE")
    try:
        error("busy", lambda: second.create(new_uuid(), VALUES))
    finally:
        first._connection.rollback()
    assert second.list(AuditFilter()).total == 1
    assert second.history(audit.id).total == 2
    first.close()
    second.close()


def test_literal_search_date_sort_and_pagination(repo):
    repo.save_profile("Tester")
    first = repo.create(new_uuid(), dict(VALUES, driver_name="A%_\\😀", station="Unique", audit_date="2024-01-01"))
    second = repo.create(new_uuid(), dict(VALUES, driver_name="Another", audit_date="2024-02-01"))
    assert repo.list(AuditFilter(driver="%_\\😀")).items == (first,)
    assert repo.list(AuditFilter(plate="TEST-1", station="unique")).items == (first,)
    assert repo.list(AuditFilter(date_from="2024-01-02", date_to="2024-02-01")).items == (second,)
    assert repo.list(AuditFilter(sort="created", page=2, page_size=1)).items == (second,)
    assert repo.list(AuditFilter(sort="-created")).items == (second, first)
    assert repo.list(AuditFilter(sort="audit_date")).items == (first, second)
    assert repo.list(AuditFilter(sort="-audit_date")).items == (second, first)
    assert repo.list(AuditFilter(page=10000, page_size=101)).items == ()


@pytest.mark.parametrize("changes", [dict(page=0), dict(page=True), dict(page=10001), dict(page_size=0), dict(page_size=102), dict(sort="id; DROP TABLE audit_records"), dict(date_from="2024-02-30"), dict(date_to=" 2024-01-01"), dict(date_from="2024-02-02", date_to="2024-01-01"), dict(driver=3), dict(include_archived="yes")])
def test_invalid_filters(repo, changes):
    error("validation", lambda: repo.list(AuditFilter(**changes)))


def test_invalid_ids_missing_record_and_revisions(repo):
    seed(repo)
    for invalid in ["bad", new_uuid().upper(), 1, None]:
        error("validation", lambda: repo.read(invalid))
    missing = new_uuid()
    error("not_found", lambda: repo.read(missing))
    error("not_found", lambda: repo.history(missing))
    audit = repo.list(AuditFilter()).items[0]
    for revision in [0, -1, True, "1"]:
        error("validation", lambda: repo.update(audit.id, revision, VALUES))
    error("validation", lambda: repo.history(audit.id, page_size=102))


@pytest.mark.parametrize("target", ["audit_records", "audit_events"])
@pytest.mark.parametrize("action", ["create", "update", "archive"])
def test_trigger_failure_rolls_back_record_and_history(repo, target, action):
    audit = seed(repo)
    operation = "INSERT" if action == "create" else "UPDATE"
    if target == "audit_events":
        operation = "INSERT"
    repo._connection.execute(f"CREATE TRIGGER refuse BEFORE {operation} ON {target} BEGIN SELECT RAISE(ABORT, 'secret path'); END")
    record_id = new_uuid()
    works = dict(create=lambda: repo.create(record_id, VALUES), update=lambda: repo.update(audit.id, 1, dict(VALUES, remarks="No")), archive=lambda: repo.archive(audit.id, 1))
    failure = error("storage", works[action])
    assert "secret" not in failure.message
    assert repo.read(audit.id) == audit
    assert repo.history(audit.id).total == 1
    assert repo.list(AuditFilter()).total == 1
    repo._connection.execute("DROP TRIGGER refuse")
    assert repo.update(audit.id, 1, dict(VALUES, remarks="Yes")).revision == 2


def test_commit_failure_uses_real_deferred_foreign_key_and_rolls_back(repo):
    audit = seed(repo)
    conn = repo._connection
    conn.execute("CREATE TEMP TABLE commit_guard (id TEXT REFERENCES audit_records(id) DEFERRABLE INITIALLY DEFERRED)")
    # A TEMP trigger can reference the main tables; the FK belongs to temp, so
    # use a deferred self-reference to make SQLite fail only at COMMIT.
    conn.execute("DROP TABLE commit_guard")
    conn.execute("CREATE TEMP TABLE commit_guard (id INTEGER PRIMARY KEY, parent INTEGER REFERENCES commit_guard(id) DEFERRABLE INITIALLY DEFERRED)")
    conn.execute("CREATE TEMP TRIGGER refuse_commit AFTER INSERT ON main.audit_events BEGIN INSERT INTO commit_guard VALUES (1, 2); END")
    error("storage", lambda: repo.update(audit.id, 1, dict(VALUES, remarks="No")))
    assert repo.read(audit.id) == audit
    assert repo.history(audit.id).total == 1
    assert conn.execute("SELECT count(*) FROM commit_guard").fetchone()[0] == 0


def test_real_sqlite_full_rolls_back(repo):
    audit = seed(repo)
    conn = repo._connection
    pages = conn.execute("PRAGMA page_count").fetchone()[0]
    conn.execute(f"PRAGMA max_page_count={pages}")
    error("full", lambda: repo.update(audit.id, 1, dict(VALUES, remarks="X" * 10000)))
    assert repo.read(audit.id) == audit
    assert repo.history(audit.id).total == 1


def test_readonly_failure_is_sanitized_and_recovers(repo):
    audit = seed(repo)
    repo._connection.execute("PRAGMA query_only=ON")
    failure = error("storage", lambda: repo.update(audit.id, 1, dict(VALUES, remarks="No")))
    assert "readonly" not in failure.message.lower()
    assert repo.read(audit.id) == audit
    repo._connection.execute("PRAGMA query_only=OFF")
    assert repo.update(audit.id, 1, dict(VALUES, remarks="Yes")).revision == 2


@pytest.mark.parametrize("operation", ["profile", "save_profile", "list", "read", "create", "update", "archive", "history", "close"])
def test_every_operation_enforces_owner_thread(repo, operation):
    audit = seed(repo)
    work = dict(profile=repo.profile, save_profile=lambda: repo.save_profile("Other"), list=lambda: repo.list(AuditFilter()), read=lambda: repo.read(audit.id), create=lambda: repo.create(new_uuid(), VALUES), update=lambda: repo.update(audit.id, 1, VALUES), archive=lambda: repo.archive(audit.id, 1), history=lambda: repo.history(audit.id), close=repo.close)[operation]
    with ThreadPoolExecutor(max_workers=1) as pool:
        error("thread", lambda: pool.submit(work).result())
    assert repo.read(audit.id) == audit


def test_closed_repository_is_typed_and_close_is_idempotent(repo):
    repo.close()
    repo.close()
    error("closed", repo.profile)


@pytest.mark.parametrize("damage", ["newer", "unversioned", "foreign", "missing_column", "extra_table", "missing_fk", "violated_fk"])
def test_schema_refusal_preserves_existing_database(tmp_path, damage):
    path = tmp_path / "test.db"
    repo = SqliteRepository(path)
    seed(repo)
    repo.close()
    with sqlite3.connect(path) as db:
        if damage == "newer": db.execute("PRAGMA user_version=2")
        if damage == "unversioned": db.execute("PRAGMA user_version=0")
        if damage == "foreign": db.execute("UPDATE app_meta SET value='foreign' WHERE key='app_id'")
        if damage == "missing_column": db.execute("ALTER TABLE audit_records RENAME COLUMN station TO secret")
        if damage == "extra_table": db.execute("CREATE TABLE foreign_data (value TEXT)")
        if damage == "missing_fk":
            db.execute("ALTER TABLE audit_events RENAME TO old_events")
            db.execute("CREATE TABLE audit_events AS SELECT * FROM old_events")
            db.execute("DROP TABLE old_events")
        if damage == "violated_fk": db.execute("UPDATE audit_records SET profile_id='missing'")
    before = path.read_bytes()
    error("schema", lambda: SqliteRepository(path))
    assert path.read_bytes() == before


def test_corrupt_database_is_never_reset(tmp_path):
    path = tmp_path / "corrupt.db"
    path.write_bytes(b"This is not a database: secret employee filename")
    before = path.read_bytes()
    failure = error("corrupt", lambda: SqliteRepository(path))
    assert path.read_bytes() == before
    assert "secret" not in failure.message


def test_foreign_unversioned_database_is_never_reset(tmp_path):
    path = tmp_path / "foreign.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE unrelated (value TEXT)")
        db.execute("INSERT INTO unrelated VALUES ('preserve')")
    before = path.read_bytes()
    error("schema", lambda: SqliteRepository(path))
    assert path.read_bytes() == before


@pytest.mark.parametrize("version", [0, 1])
def test_foreign_views_are_refused_without_database_changes(tmp_path, version):
    path = tmp_path / "views.db"
    if version:
        SqliteRepository(path).close()
    with sqlite3.connect(path) as db:
        db.execute("CREATE VIEW foreign_view AS SELECT 'preserve' AS value")
    before = path.read_bytes()
    error("schema", lambda: SqliteRepository(path))
    assert path.read_bytes() == before


def test_database_constraint_literal_changes_are_refused(tmp_path):
    path = tmp_path / "weak.db"
    SqliteRepository(path).close()
    # SQLite accepts these exact lower-case actions, unlike the app contract.
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE audit_events")
        db.execute("CREATE TABLE audit_events (id TEXT PRIMARY KEY NOT NULL, audit_id TEXT NOT NULL REFERENCES audit_records(id), revision INTEGER NOT NULL CHECK(revision >= 1), action TEXT NOT NULL CHECK(action IN ('create','update','archive')), actor_name TEXT NOT NULL, actor_profile_id TEXT NOT NULL, created_at TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL, UNIQUE(audit_id, revision))")
    before = path.read_bytes()
    error("schema", lambda: SqliteRepository(path))
    assert path.read_bytes() == before


def test_profile_failure_rolls_back_without_losing_existing_name(repo):
    profile = repo.save_profile("Original")
    repo._connection.execute("CREATE TRIGGER refuse_profile BEFORE UPDATE ON local_profile BEGIN SELECT RAISE(ABORT, 'private path'); END")
    error("storage", lambda: repo.save_profile("Changed"))
    assert repo.profile() == profile


def test_foreign_keys_enforce_record_and_event_links(repo):
    audit = seed(repo)
    with pytest.raises(sqlite3.IntegrityError):
        repo._connection.execute("UPDATE audit_records SET profile_id='missing' WHERE id=?", (audit.id,))
    with pytest.raises(sqlite3.IntegrityError):
        repo._connection.execute("UPDATE audit_events SET audit_id='missing' WHERE audit_id=?", (audit.id,))
    assert repo.read(audit.id) == audit


def test_list_count_and_rows_share_one_read_snapshot(tmp_path):
    path = tmp_path / "snapshot.db"
    first = SqliteRepository(path)
    audit = seed(first)
    first._connection.execute("PRAGMA journal_mode=WAL")
    second = SqliteRepository(path)
    inserted = []

    def write_between_count_and_rows(statement):
        if statement.startswith("SELECT * FROM audit_records") and not inserted:
            inserted.append(second.create(new_uuid(), VALUES))

    first._connection.set_trace_callback(write_between_count_and_rows)
    page = first.list(AuditFilter())
    first._connection.set_trace_callback(None)
    assert len(inserted) == 1
    assert page.total == 1 and page.items == (audit,)
    assert first.list(AuditFilter()).total == 2
    first.close()
    second.close()


def test_bad_stored_history_returns_sanitized_corruption(repo):
    audit = seed(repo)
    repo._connection.execute("UPDATE audit_events SET after_json=?", ('secret invalid JSON',))
    failure = error("corrupt", lambda: repo.history(audit.id))
    assert "secret" not in failure.message
    error("corrupt", lambda: repo.create(audit.id, VALUES))


def test_inaccessible_database_location_returns_sanitized_storage_error(tmp_path):
    path = tmp_path / "private-missing-folder" / "test.db"
    failure = error("storage", lambda: SqliteRepository(path))
    assert "private" not in failure.message and not path.exists()


def test_public_methods_accept_documented_id_keyword(repo):
    repo.save_profile("Tester")
    identifier = new_uuid()
    audit = repo.create(id=identifier, values=VALUES)
    assert repo.read(id=identifier) == audit
    assert repo.update(id=identifier, expected_revision=1, values=VALUES) == audit
    assert repo.history(id=identifier).total == 1
    assert repo.archive(id=identifier, expected_revision=1).revision == 2


@pytest.mark.parametrize("field,value", [("name", ""), ("name", "\u0085  "), ("name", "X" * 201), ("id", "private-invalid-profile-id")])
def test_malformed_stored_profile_is_rejected_by_bootstrap_without_repair(tmp_path, field, value):
    path = tmp_path / "malformed-profile.db"
    repo = SqliteRepository(path)
    repo.save_profile("Original Auditor")
    repo._connection.execute(f"UPDATE local_profile SET {field}=?", (value,))
    repo.close()
    before = path.read_bytes()
    repo = SqliteRepository(path)
    try:
        failure = error("corrupt", repo.profile)
        assert "private" not in failure.message
        assert "Original Auditor" not in failure.message
        if value:
            assert value not in failure.message
        error("corrupt", lambda: repo.save_profile("Replacement Auditor"))
        assert repo._connection.execute(f"SELECT {field} FROM local_profile").fetchone()[0] == value
        assert repo._connection.execute("SELECT count(*) FROM audit_records").fetchone()[0] == 0
        assert repo._connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 0
    finally:
        repo.close()
    assert path.read_bytes() == before


@pytest.mark.parametrize("field,value", [("name", ""), ("name", "X" * 201), ("id", "private-invalid-profile-id")])
@pytest.mark.parametrize("operation", ["create", "update", "archive"])
def test_malformed_stored_actor_rejects_audit_and_history_writes(repo, field, value, operation):
    audit = seed(repo)
    # Deliberately introduce malformed persisted identity through real SQLite.
    # Keep the existing audit snapshot intact to exercise actor loading itself.
    repo._connection.execute("PRAGMA foreign_keys=OFF")
    repo._connection.execute(f"UPDATE local_profile SET {field}=?", (value,))
    repo._connection.execute("PRAGMA foreign_keys=ON")
    work = {
        "create": lambda: repo.create(new_uuid(), VALUES),
        "update": lambda: repo.update(audit.id, 1, dict(VALUES, remarks="Changed")),
        "archive": lambda: repo.archive(audit.id, 1),
    }[operation]
    failure = error("corrupt", work)
    assert "private" not in failure.message
    assert repo._connection.execute("SELECT count(*) FROM audit_records").fetchone()[0] == 1
    assert repo._connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 1
    assert repo._connection.execute(f"SELECT {field} FROM local_profile").fetchone()[0] == value
    assert repo.read(audit.id) == audit
    assert repo.history(audit.id).items[0].after == audit
