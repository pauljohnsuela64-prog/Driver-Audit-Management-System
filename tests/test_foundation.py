from datetime import date, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, StatementError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from backend.core.config import database_url
from backend.core.database import make_engine, session_scope, utcnow
from backend.models import AuditEvent, AuditRecord, AuthSession, Base, User
from backend.schemas.audit import AuditFields, AuditRead


def user(**overrides):
    return User(**(dict(username="auditor", full_name="Test Auditor", password_hash="test-only-hash", role="AUDITOR") | overrides))


def audit(uid, **overrides):
    return AuditRecord(**(dict(driver_name="Driver", audit_date=date(2026, 10, 25), station="Manila", plate_number="ABC123", audited_by_user_id=uid, audited_by_name="Test Auditor") | overrides))


def test_tables_and_business_fields():
    assert set(Base.metadata.tables) == {"users", "audit_records", "audit_events", "auth_sessions"}
    assert set(AuditFields.model_fields) == {"driver_name", "helper_name", "audit_date", "station", "plate_number", "remarks", "audited_by_name"}
    assert not AuditRecord.__table__.c.plate_number.unique
    assert AuditRecord.__table__.c.idempotency_key.unique
    assert len(AuditRecord.__table__.foreign_keys) == 3


def test_optional_duplicate_plates_relationships_and_schema(session):
    u = user()
    session.add(u)
    session.flush()
    a, b = audit(u.id), audit(u.id)
    session.add_all([a, b])
    session.flush()
    event = AuditEvent(audit=a, actor=u, action="CREATE", after_data={"driver_name": "Driver"})
    token = AuthSession(user=u, token_hash="a" * 64, expires_at=utcnow() + timedelta(hours=1))
    session.add_all([event, token])
    session.commit()
    session.expire_all()
    assert a.helper_name is None and a.remarks is None
    assert a.version == 1 and a.auditor is u and a in u.audits
    assert event in a.events and event.actor is u and token in u.sessions
    assert event.after_data == {"driver_name": "Driver"}
    assert event.before_data is None
    assert a.created_at.tzinfo == timezone.utc
    assert AuditRead.model_validate(a).plate_number == "ABC123"


@pytest.mark.parametrize("field,value", [("driver_name", None), ("audit_date", None), ("station", None), ("plate_number", None), ("audited_by_name", None), ("driver_name", " "), ("version", 0), ("audited_by_user_id", 999), ("updated_by_user_id", 999), ("deleted_at", utcnow()), ("idempotency_key", "")])
def test_audit_constraints(session, field, value):
    u = user()
    session.add(u)
    session.flush()
    a = audit(u.id, **{field: value})
    session.add(a)
    if field == "version":
        # The ORM initializes versions to 1; exercise the DB constraint directly.
        session.flush()
        with pytest.raises(IntegrityError):
            session.execute(text("UPDATE audit_records SET version=0 WHERE id=:id"), {"id": a.id})
        return
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize("changes", [{"role": "OWNER"}, {"username": ""}, {"full_name": " "}, {"password_hash": ""}])
def test_user_constraints(session, changes):
    session.add(user(**changes))
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize("kind", ["username", "idempotency_key", "token_hash"])
def test_unique_constraints(session, kind):
    u = user()
    session.add(u)
    session.flush()
    if kind == "username":
        session.add(user())
    elif kind == "idempotency_key":
        session.add_all([audit(u.id, idempotency_key="same"), audit(u.id, idempotency_key="same")])
    else:
        session.add_all([AuthSession(user_id=u.id, token_hash="a" * 64, expires_at=utcnow() + timedelta(hours=1)) for _ in range(2)])
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize("kind", ["event_actor", "event_audit", "action", "session_user", "expiry", "hash", "revocation"])
def test_event_session_constraints(session, kind):
    u = user()
    session.add(u)
    session.flush()
    a = audit(u.id)
    session.add(a)
    session.flush()
    now = utcnow()
    if kind in {"event_actor", "event_audit", "action"}:
        session.add(AuditEvent(audit_id=999 if kind == "event_audit" else a.id, actor_user_id=999 if kind == "event_actor" else u.id, action="INVALID" if kind == "action" else "CREATE"))
    else:
        session.add(AuthSession(user_id=999 if kind == "session_user" else u.id, token_hash="bad" if kind == "hash" else "a" * 64, created_at=now, expires_at=now - timedelta(hours=1) if kind == "expiry" else now + timedelta(hours=1), revoked_at=now - timedelta(hours=1) if kind == "revocation" else None))
    with pytest.raises(IntegrityError):
        session.flush()


def test_restrict_deletion(session):
    u = user()
    session.add(u)
    session.flush()
    a = audit(u.id)
    session.add(a)
    session.flush()
    session.add(AuditEvent(audit_id=a.id, actor_user_id=u.id, action="CREATE"))
    session.flush()
    with pytest.raises(IntegrityError):
        session.execute(text("DELETE FROM audit_records WHERE id=:id"), {"id": a.id})


def test_optimistic_version(engine):
    with session_scope(engine) as s:
        u = user()
        s.add(u)
        s.flush()
        a = audit(u.id)
        s.add(a)
        s.flush()
        audit_id = a.id
    with Session(engine) as one, Session(engine) as two:
        first, second = one.get(AuditRecord, audit_id), two.get(AuditRecord, audit_id)
        first.remarks = "first"
        one.commit()
        assert first.version == 2
        second.remarks = "second"
        with pytest.raises(StaleDataError):
            two.commit()


def test_session_commit_rollback_and_close(engine):
    with session_scope(engine) as s:
        s.add(user())
    with pytest.raises(RuntimeError):
        with session_scope(engine) as s:
            s.add(user(username="rollback"))
            s.flush()
            raise RuntimeError("abort")
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(User)) == 1
    with session_scope(engine) as s:
        assert s.scalar(text("SELECT 1")) == 1


def test_connection_failure(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'missing' / 'no.db').as_posix()}")
    try:
        with pytest.raises(OperationalError):
            with engine.connect():
                pass
    finally:
        engine.dispose()


def test_timezone_conversion_and_reject_naive(session):
    u = user(created_at=utcnow().astimezone(timezone(timedelta(hours=8))))
    session.add(u)
    session.commit()
    session.expire_all()
    assert u.created_at.utcoffset() == timedelta(0)
    u.updated_at = utcnow().replace(tzinfo=None)
    with pytest.raises(StatementError, match="timezone"):
        session.flush()


@pytest.mark.parametrize("bad", [{"driver_name": " "}, {"station": "x" * 151}, {"plate_number": "x" * 31}, {"audit_date": "bad"}, {"gps": "unapproved"}])
def test_schema_validation(bad):
    data = dict(driver_name="Driver", audit_date="2026-10-25", station="Manila", plate_number="ABC123", audited_by_name="Auditor")
    with pytest.raises(ValidationError):
        AuditFields(**(data | bad))


@pytest.mark.parametrize("url", ["", "sqlite://", "mysql+pymysql://root:secret@localhost/driver_audit_db", "mysql+pymysql://dams:secret@localhost/other_project", "mysql+pymysql://dams@localhost/driver_audit_db"])
def test_configuration_rejects_unsafe_target(monkeypatch, url):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(ValueError):
        database_url()


def test_configuration_accepts_dams(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://dams:test-only@localhost/driver_audit_db")
    assert database_url().database == "driver_audit_db"
