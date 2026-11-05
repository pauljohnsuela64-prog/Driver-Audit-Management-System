from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from desktop.offline.models import AuditFilter, OfflineError, new_uuid
from desktop.offline.repository import SqliteRepository

VALUES = dict(driver_name='Fictional \u99d5\u99db', helper_name=None, audit_date='2026-11-06', station='North', plate_number='000123', remarks='Long\nUnicode \U0001f69a')


def stores(tmp_path):
    a, b = SqliteRepository(tmp_path/'a.db'), SqliteRepository(tmp_path/'b.db')
    a.save_profile('Origin Auditor')
    b.save_profile('Importing Auditor')
    return a, b


def test_new_duplicate_conflict_and_imported_history_keep_local_profile(tmp_path):
    from desktop.offline.transfer_store import TransferStore
    a, b = stores(tmp_path)
    try:
        audit = a.create(new_uuid(), VALUES)
        updated = a.update(audit.id, 1, VALUES | {'station': 'Changed'})
        archived = a.archive(audit.id, 2)
        local_profile = b.profile()
        raw = TransferStore(a).export()
        preview = TransferStore(b).preview(raw)
        assert preview.new_ids == (audit.id,)
        result = TransferStore(b).apply(raw, preview)
        assert (result.imported, result.duplicates, result.conflicts) == (1, 0, 0)
        assert b.read(audit.id) == archived and b.profile() == local_profile
        assert b.history(audit.id).items == a.history(audit.id).items
        assert b._connection.execute('PRAGMA foreign_key_check').fetchall() == []
        duplicate = TransferStore(b).preview(raw)
        assert duplicate.duplicate_ids == (audit.id,)
        assert TransferStore(b).apply(raw, duplicate).imported == 0
        b.close()
        b = SqliteRepository(tmp_path/'b.db')
        assert b.read(audit.id) == archived
    finally:
        a.close(); b.close()


def test_preview_race_rejects_without_reclassifying_consent(tmp_path):
    from desktop.offline.transfer_store import TransferStore
    a, b = stores(tmp_path)
    try:
        audit = a.create(new_uuid(), VALUES)
        raw = TransferStore(a).export()
        old = TransferStore(b).preview(raw)
        TransferStore(b).apply(raw, old)
        with pytest.raises(OfflineError): TransferStore(b).apply(raw, old)
        b.update(audit.id, 1, VALUES | {'station': 'Local edit'})
        preview = TransferStore(b).preview(raw)
        assert preview.conflict_ids == (audit.id,)
        assert TransferStore(b).apply(raw, preview).conflicts == 1
        assert b.read(audit.id).station == 'Local edit'
    finally:
        a.close(); b.close()


def test_insert_failure_rolls_back_records_events_registry_and_receipt(tmp_path):
    from desktop.offline.transfer_store import TransferStore
    a, b = stores(tmp_path)
    try:
        a.create(new_uuid(), VALUES)
        raw = TransferStore(a).export()
        preview = TransferStore(b).preview(raw)
        b._connection.execute("CREATE TRIGGER fail_event BEFORE INSERT ON audit_events BEGIN SELECT RAISE(ABORT,'test'); END")
        with pytest.raises(OfflineError): TransferStore(b).apply(raw, preview)
        assert b.list(AuditFilter(include_archived=True)).total == 0
        assert b._connection.execute('SELECT count(*) FROM audit_events').fetchone()[0] == 0
        assert b._connection.execute('SELECT count(*) FROM transfer_receipts').fetchone()[0] == 0
        assert b._connection.execute('SELECT count(*) FROM auditor_identities').fetchone()[0] == 1
    finally:
        a.close(); b.close()


def test_filters_empty_export_and_cancellation(tmp_path):
    from desktop.offline.transfer_store import TransferStore
    from desktop.offline.transfer import decode_transfer
    a, b = stores(tmp_path)
    try:
        a.create(new_uuid(), VALUES)
        assert not decode_transfer(TransferStore(a).export(date_from='2026-11-07')).audits
        raw = TransferStore(a).export()
        with pytest.raises(OfflineError): TransferStore(a).export(cancel=lambda: True)
        with pytest.raises(OfflineError): TransferStore(b).apply(raw, TransferStore(b).preview(raw), cancel=lambda: True)
        assert not b.list(AuditFilter()).items
    finally:
        a.close(); b.close()


def test_same_package_uuid_different_content_rejected(tmp_path):
    from desktop.offline.transfer_store import TransferStore
    from desktop.offline.transfer import decode_transfer, encode_transfer
    a, b = stores(tmp_path)
    try:
        audit = a.create(new_uuid(), VALUES)
        raw = TransferStore(a).export()
        TransferStore(b).apply(raw, TransferStore(b).preview(raw))
        p = decode_transfer(raw)
        changed = dict(p.manifest, exported_at='2026-11-07T01:00:00.000000Z')
        bad = encode_transfer(changed, p.audits, p.events)
        with pytest.raises(OfflineError): TransferStore(b).preview(bad)
    finally:
        a.close(); b.close()
