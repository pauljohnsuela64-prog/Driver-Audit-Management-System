"""Account creation and read-only queries; no account mutation operations."""
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from backend.core.errors import ServiceError
from backend.core.security import hash_password
from backend.models import User


def create_user(session, payload):
    user = User(username=payload.username, full_name=payload.full_name, role=payload.role,
                password_hash=hash_password(payload.password.get_secret_value()), is_active=True)
    session.add(user)
    try:
        # The unique index arbitrates simultaneous creations. Propagate failure to
        # the request transaction so it rolls back before returning the error.
        session.flush()
    except IntegrityError as exc:
        if (getattr(exc.orig, "sqlite_errorcode", None) == 2067
                or (session.bind.dialect.name == "mysql" and exc.orig.args[0] == 1062)):
            raise ServiceError(409, "username_exists", "Username already exists") from None
        raise
    return user


def list_users(session, page, page_size, search):
    conditions = []
    if search:
        conditions.append(or_(User.username.contains(search, autoescape=True),
                              User.full_name.contains(search, autoescape=True)))
    total = session.scalar(select(func.count()).select_from(User).where(*conditions))
    users = session.scalars(select(User).where(*conditions).order_by(User.id)
                            .offset((page - 1) * page_size).limit(page_size)).all()
    return users, total


def get_user(session, user_id):
    user = session.get(User, user_id)
    if user is None:
        raise ServiceError(404, "not_found", "Account not found")
    return user
