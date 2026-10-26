"""Account creation, limited profile editing and safe account queries."""
from sqlalchemy import func, or_, select, update
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
        if username_conflict(session, exc):
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


def username_conflict(session, exc):
    return (getattr(exc.orig, "sqlite_errorcode", None) == 2067
            or (session.bind.dialect.name == "mysql" and exc.orig.args[0] == 1062))


def update_user(session, user_id, payload):
    try:
        # Write only supplied fields. Database UPDATE locks serialize competing
        # writers without overwriting unrelated fields from a stale ORM instance.
        result = session.execute(update(User).where(User.id == user_id)
                                 .values(**payload.model_dump(exclude_unset=True))
                                 .execution_options(synchronize_session=False))
    except IntegrityError as exc:
        if username_conflict(session, exc):
            raise ServiceError(409, "username_exists", "Username already exists") from None
        raise
    if result.rowcount == 0:
        raise ServiceError(404, "not_found", "Account not found")
    # Refresh even when authentication already loaded this user. A locking read
    # also bypasses an older MySQL REPEATABLE READ snapshot.
    return session.scalar(select(User).where(User.id == user_id).with_for_update()
                          .execution_options(populate_existing=True))
