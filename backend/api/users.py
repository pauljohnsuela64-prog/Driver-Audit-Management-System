from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from pydantic import StringConstraints

from backend.api.dependencies import DatabaseSession, require_roles
from backend.schemas.users import AccountPage, AccountResponse, UserCreate
from backend.services.users import create_user, get_user, list_users

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_roles("ADMIN"))])
Search = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


@router.post("", response_model=AccountResponse, status_code=201)
def create(payload: UserCreate, session: DatabaseSession):
    return AccountResponse.model_validate(create_user(session, payload))


@router.get("", response_model=AccountPage)
def listing(session: DatabaseSession,
            page: Annotated[int, Query(ge=1, le=10000)] = 1,
            page_size: Annotated[int, Query(ge=1, le=100)] = 50,
            search: Annotated[Search | None, Query()] = None):
    users, total = list_users(session, page, page_size, search)
    return AccountPage(items=users, total=total, page=page, page_size=page_size)


@router.get("/{user_id}", response_model=AccountResponse)
def read(user_id: Annotated[int, Path(ge=1)], session: DatabaseSession):
    return AccountResponse.model_validate(get_user(session, user_id))
