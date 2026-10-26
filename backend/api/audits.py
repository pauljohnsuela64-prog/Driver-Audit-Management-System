import re
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Response
from sqlalchemy import func, select

from backend.api.dependencies import DatabaseSession, Identity
from backend.core.errors import ServiceError
from backend.models import AuditRecord, AuditEvent
from backend.schemas.audit_api import (AuditCreate, AuditPatch, AuditResponse, AuditPage,
                                      CalendarDate, EventPage)
from backend.services.audits import create_record, get_record, mutate_record

router = APIRouter(prefix="/audits", tags=["audits"])
Page = Annotated[int, Query(ge=1, le=10000)]
PageSize = Annotated[int, Query(ge=1, le=100)]
Search = Annotated[str | None, Query(min_length=1, max_length=200)]


def version_header(value):
    if value is None:
        raise ServiceError(428, "precondition_required", "If-Match is required")
    if not re.fullmatch(r'"[1-9][0-9]{0,9}"', value):
        raise ServiceError(422, "invalid_request", "If-Match must be a quoted positive version")
    return int(value[1:-1])


def respond(response, record):
    response.headers["ETag"] = f'"{record.version}"'
    return AuditResponse.model_validate(record)


@router.post("", response_model=AuditResponse, status_code=201)
def create(payload: AuditCreate, session: DatabaseSession, identity: Identity, response: Response,
           idempotency_key: Annotated[UUID | None, Header()] = None):
    record, created = create_record(session, identity[1], payload,
                                    str(idempotency_key) if idempotency_key else None)
    response.status_code = 201 if created else 200
    return respond(response, record)


@router.get("", response_model=AuditPage)
def listing(session: DatabaseSession, identity: Identity, page: Page = 1, page_size: PageSize = 50,
            driver_name: Search = None, plate_number: Search = None, station: Search = None,
            date_from: CalendarDate | None = None, date_to: CalendarDate | None = None,
            audited_by_user_id: Annotated[int | None, Query(ge=1)] = None,
            include_deleted: bool = False,
            sort: Literal["id", "-id", "audit_date", "-audit_date"] = "-id"):
    if include_deleted and identity[1].role != "ADMIN":
        raise ServiceError(403, "forbidden", "Insufficient permission")
    if date_from and date_to and date_from > date_to:
        raise ServiceError(422, "invalid_request", "Invalid date range")
    conditions = [] if include_deleted else [AuditRecord.deleted_at.is_(None)]
    for field, value in [(AuditRecord.driver_name, driver_name), (AuditRecord.plate_number, plate_number),
                         (AuditRecord.station, station)]:
        if value is not None:
            conditions.append(field.contains(value, autoescape=True))
    if date_from:
        conditions.append(AuditRecord.audit_date >= date_from)
    if date_to:
        conditions.append(AuditRecord.audit_date <= date_to)
    if audited_by_user_id is not None:
        conditions.append(AuditRecord.audited_by_user_id == audited_by_user_id)
    field = AuditRecord.audit_date if "audit_date" in sort else AuditRecord.id
    ordering = (field.desc(), AuditRecord.id.desc()) if sort.startswith("-") else (field.asc(), AuditRecord.id.asc())
    total = session.scalar(select(func.count()).select_from(AuditRecord).where(*conditions))
    items = session.scalars(select(AuditRecord).where(*conditions).order_by(*ordering)
                            .offset((page - 1) * page_size).limit(page_size)).all()
    return AuditPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/{audit_id}", response_model=AuditResponse)
def read(audit_id: int, session: DatabaseSession, identity: Identity, response: Response,
         include_deleted: bool = False):
    return respond(response, get_record(session, audit_id, identity[1], include_deleted))


@router.patch("/{audit_id}", response_model=AuditResponse)
def update(audit_id: int, payload: AuditPatch, session: DatabaseSession, identity: Identity,
           response: Response, if_match: Annotated[str | None, Header()] = None):
    record = mutate_record(session, identity[1], audit_id, version_header(if_match), payload)
    return respond(response, record)


@router.delete("/{audit_id}", status_code=204)
def delete(audit_id: int, session: DatabaseSession, identity: Identity,
           if_match: Annotated[str | None, Header()] = None):
    mutate_record(session, identity[1], audit_id, version_header(if_match))
    return Response(status_code=204)


@router.get("/{audit_id}/history", response_model=EventPage)
def history(audit_id: int, session: DatabaseSession, identity: Identity, page: Page = 1,
            page_size: PageSize = 50, include_deleted: bool = False):
    get_record(session, audit_id, identity[1], include_deleted)
    condition = AuditEvent.audit_id == audit_id
    total = session.scalar(select(func.count()).select_from(AuditEvent).where(condition))
    items = session.scalars(select(AuditEvent).where(condition).order_by(AuditEvent.id)
                            .offset((page - 1) * page_size).limit(page_size)).all()
    return EventPage(items=items, total=total, page=page, page_size=page_size)
