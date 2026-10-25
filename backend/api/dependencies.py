from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core.database import session_scope
from backend.core.errors import ServiceError, unauthorized
from backend.core.security import TOKEN_PATTERN
from backend.repositories.auth import AuthRepository
from backend.services.auth import AuthService

bearer = HTTPBearer(auto_error=False)


def get_session(request: Request):
    # Commit/rollback completes before FastAPI sends a successful response.
    with session_scope(request.app.state.engine) as session:
        yield session


DatabaseSession = Annotated[Session, Depends(get_session, scope="function")]


def get_auth_service(session: DatabaseSession):
    return AuthService(AuthRepository(session))


Auth = Annotated[AuthService, Depends(get_auth_service)]


def current_identity(auth: Auth, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if not credentials or credentials.scheme.lower() != "bearer" or not TOKEN_PATTERN.fullmatch(credentials.credentials):
        raise unauthorized()
    return auth.authenticate(credentials.credentials)


Identity = Annotated[tuple, Depends(current_identity)]


def require_roles(*roles: str):
    if not roles or not set(roles) <= {"ADMIN", "AUDITOR"}:
        raise ValueError("Unknown role")

    def permitted(identity: Identity):
        if identity[1].role not in roles:
            raise ServiceError(403, "forbidden", "Insufficient permission")
        return identity[1]

    return permitted
