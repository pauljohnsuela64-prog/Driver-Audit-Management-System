"""Audit mutations and their append-only history share the request transaction."""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from backend.core.database import utcnow
from backend.core.errors import ServiceError
from backend.models import AuditRecord, AuditEvent
from backend.schemas.audit_api import AuditCreate, AuditResponse


def begin_sqlite_write(session):
    # sqlite3 legacy mode does not BEGIN on SELECT or SAVEPOINT. Ensure nested
    # creation is inside a real outer transaction; serialize local SQLite writes.
    connection = session.connection()
    if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN IMMEDIATE")


def conflict():
    return ServiceError(409, "conflict", "Audit request conflicts with current state")


def snapshot(record):
    return AuditResponse.model_validate(record).model_dump(mode="json")


def get_record(session, audit_id, user, include_deleted=False, lock=False):
    if include_deleted and user.role != "ADMIN":
        raise ServiceError(403, "forbidden", "Insufficient permission")
    query = select(AuditRecord).where(AuditRecord.id == audit_id)
    if not include_deleted:
        query = query.where(AuditRecord.deleted_at.is_(None))
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    record = session.scalar(query)
    if record is None:
        raise ServiceError(404, "not_found", "Audit not found")
    return record


def add_event(session, record, user, action, before=None):
    session.add(AuditEvent(audit_id=record.id, actor_user_id=user.id, action=action,
                           before_data=before, after_data=snapshot(record)))
    session.flush()


def replay(session, record, user, payload):
    # Locking reads see a winning concurrent insert under MySQL REPEATABLE READ.
    event = session.scalar(select(AuditEvent).where(AuditEvent.audit_id == record.id,
                           AuditEvent.action == "CREATE").order_by(AuditEvent.id).with_for_update(read=True))
    original = None if event is None else {k: event.after_data.get(k) for k in AuditCreate.model_fields}
    if (record.audited_by_user_id != user.id or record.deleted_at is not None
            or original != payload.model_dump(mode="json")):
        raise conflict()
    return record, False


def create_record(session, user, payload, key):
    begin_sqlite_write(session)
    if key:
        existing = session.scalar(select(AuditRecord).where(AuditRecord.idempotency_key == key))
        if existing:
            existing = session.scalar(select(AuditRecord).where(AuditRecord.id == existing.id)
                                      .with_for_update().execution_options(populate_existing=True))
            return replay(session, existing, user, payload)
    try:
        # Do not gap-lock missing keys: the unique index arbitrates competing inserts.
        with session.begin_nested():
            record = AuditRecord(**payload.model_dump(), audited_by_user_id=user.id,
                                 audited_by_name=user.full_name, idempotency_key=key)
            session.add(record)
            session.flush()
            add_event(session, record, user, "CREATE")
        return record, True
    except IntegrityError:
        if key:
            existing = session.scalar(select(AuditRecord).where(AuditRecord.idempotency_key == key)
                                      .with_for_update().execution_options(populate_existing=True))
            if existing:
                return replay(session, existing, user, payload)
        raise


def mutate_record(session, user, audit_id, version, patch=None):
    begin_sqlite_write(session)
    if patch is None and user.role != "ADMIN":
        raise ServiceError(403, "forbidden", "Insufficient permission")
    record = get_record(session, audit_id, user, lock=True)
    if user.role != "ADMIN" and record.audited_by_user_id != user.id:
        raise ServiceError(403, "forbidden", "Insufficient permission")
    if record.version != version:
        raise ServiceError(412, "version_mismatch", "Audit version has changed")
    before = snapshot(record)
    if patch is None:
        record.deleted_at, record.deleted_by_user_id = utcnow(), user.id
    else:
        for key, value in patch.model_dump(exclude_unset=True).items():
            setattr(record, key, value)
    record.updated_by_user_id = user.id
    # Even an accepted no-op PATCH is an event and advances the version.
    record.updated_at = utcnow()
    session.flush()
    add_event(session, record, user, "DELETE" if patch is None else "UPDATE", before)
    return record
