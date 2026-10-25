"""One-time administrator creation and explicit local account recovery."""
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from backend.core.database import utcnow
from backend.core.errors import ServiceError
from backend.core.security import hash_password
from backend.models import AuthSession, User
from backend.schemas.auth import BootstrapRequest


def bootstrap_admin(engine, request: BootstrapRequest, *, recover=False):
    encoded = hash_password(request.password.get_secret_value())
    with engine.connect() as connection:
        locked = False
        try:
            if engine.dialect.name == "mysql":
                # Serialize setup across processes without new tables or grants.
                locked = connection.scalar(text("SELECT GET_LOCK(:name, 5)"),
                                           {"name": f"dams-bootstrap:{engine.url.database}"}) == 1
                connection.commit()
                if not locked:
                    raise ServiceError(409, "setup_busy", "Administrator setup is already running")
            with Session(bind=connection) as session, session.begin():
                if recover:
                    user = session.scalar(select(User).where(User.username == request.username).with_for_update())
                    if user is None or user.role != "ADMIN":
                        raise ServiceError(409, "recovery_refused", "An existing administrator is required")
                    user.password_hash = encoded
                    user.is_active = True
                    session.execute(update(AuthSession).where(
                        AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)
                    ).values(revoked_at=utcnow()))
                else:
                    if session.scalar(select(User.id).limit(1)) is not None:
                        raise ServiceError(409, "setup_refused", "Users already exist; use explicit recovery")
                    session.add(User(username=request.username, full_name=request.full_name,
                                     password_hash=encoded, role="ADMIN", is_active=True))
        finally:
            if locked:
                connection.execute(text("SELECT RELEASE_LOCK(:name)"),
                                   {"name": f"dams-bootstrap:{engine.url.database}"})
                connection.commit()
