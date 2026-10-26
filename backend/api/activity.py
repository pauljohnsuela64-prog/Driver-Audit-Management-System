from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from backend.api.dependencies import DatabaseSession, require_roles
from backend.models import AdminActivityEvent
from backend.schemas.activity import Action, ActivityPage

router = APIRouter(prefix="/admin-activity", tags=["administrator activity"],
                   dependencies=[Depends(require_roles("ADMIN"))])


@router.get("", response_model=ActivityPage)
def listing(session: DatabaseSession, page: Annotated[int, Query(ge=1, le=10000)] = 1,
            page_size: Annotated[int, Query(ge=1, le=100)] = 50, action: Action | None = None,
            actor_user_id: Annotated[int | None, Query(ge=1)] = None,
            target_user_id: Annotated[int | None, Query(ge=1)] = None):
    filters = []
    for field, value in [(AdminActivityEvent.action, action), (AdminActivityEvent.actor_user_id, actor_user_id),
                         (AdminActivityEvent.target_user_id, target_user_id)]:
        if value is not None:
            filters.append(field == value)
    total = session.scalar(select(func.count()).select_from(AdminActivityEvent).where(*filters))
    items = session.scalars(select(AdminActivityEvent).where(*filters).order_by(AdminActivityEvent.id.desc())
                            .offset((page-1)*page_size).limit(page_size)).all()
    return ActivityPage(items=items, total=total, page=page, page_size=page_size)
