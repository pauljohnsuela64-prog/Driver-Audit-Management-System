"""Account creation, limited profile editing and safe account queries."""
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from backend.core.database import utcnow
from backend.core.errors import ServiceError, unauthorized
from backend.core.security import hash_password, verify_password
from backend.models import AuthSession, User


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


def update_access(session, user_id, payload, identity):
    observed = session.execute(select(User.role, User.is_active).where(User.id == user_id)).first()
    if observed is None:
        raise ServiceError(404, "not_found", "Account not found")
    lock_account_guard(session)
    actor = current_locked_admin(session, identity)
    now = utcnow()
    user = session.scalar(select(User).where(User.id == user_id).with_for_update()
                          .execution_options(populate_existing=True))
    if user is None:
        raise ServiceError(404, "not_found", "Account not found")
    if (user.role, user.is_active) != tuple(observed):
        raise ServiceError(409, "access_conflict", "Account access changed; reload before retrying")
    role = payload.role if "role" in payload.model_fields_set else user.role
    active = payload.is_active if "is_active" in payload.model_fields_set else user.is_active
    if user.id == actor.id and (role != "ADMIN" or not active):
        raise ServiceError(409, "self_access_change", "Cannot demote or deactivate your own account")
    if user.role == "ADMIN" and user.is_active and (role != "ADMIN" or not active):
        admins = session.scalars(select(User.id).where(User.role == "ADMIN", User.is_active.is_(True))
                                 .order_by(User.id).with_for_update()).all()
        if len(admins) <= 1:
            raise ServiceError(409, "last_admin", "An active administrator must remain")
    if role != user.role or active != user.is_active:
        user.role, user.is_active = role, active
        session.flush()
        revoke_user_sessions(session, user.id, now, active_only=True)
    return user


def lock_account_guard(session):
    # The lowest user ID is a permanent transaction guard: accounts are never
    # deleted. All access changes take it first, including changes to other rows.
    # SQLite has no row locks, so acquire its database write lock explicitly.
    connection = session.connection()
    if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    session.scalar(select(User.id).order_by(User.id).limit(1).with_for_update())



def current_locked_user(session, identity):
    # Authentication may have happened before waiting for the guard. Revalidate
    # the caller and token with current locking reads before granting authority.
    pair = session.execute(select(AuthSession, User).join(User, User.id == AuthSession.user_id)
                           .where(AuthSession.id == identity[0].id, User.id == identity[1].id)
                           .with_for_update().execution_options(populate_existing=True)).first()
    now = utcnow()
    if (pair is None or pair[0].revoked_at is not None or pair[0].expires_at <= now
            or not pair[1].is_active or pair[1].role not in {"ADMIN", "AUDITOR"}):
        raise unauthorized()
    return pair[1]


def current_locked_admin(session, identity):
    actor = current_locked_user(session, identity)
    if actor.role != "ADMIN":
        raise ServiceError(403, "forbidden", "Insufficient permission")
    return actor


def revoke_user_sessions(session, user_id, now, *, active_only=False):
    statement = update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    if active_only:
        statement = statement.where(AuthSession.expires_at > now)
    session.execute(statement.values(revoked_at=now).execution_options(synchronize_session=False))


def reset_user_password(session, user_id, payload, identity):
    lock_account_guard(session)
    actor = current_locked_admin(session, identity)
    if not verify_password(actor.password_hash, payload.admin_password.get_secret_value()):
        raise unauthorized()
    if user_id == actor.id:
        raise ServiceError(409, "self_reset", "Use a separate self-service password change flow")
    target = session.scalar(select(User).where(User.id == user_id).with_for_update()
                            .execution_options(populate_existing=True))
    if target is None:
        raise ServiceError(404, "not_found", "Account not found")
    # Login locks this same user row before password verification/session insert.
    # Every pre-reset login must finish before we replace the hash and revoke.
    target.password_hash = hash_password(payload.new_password.get_secret_value())
    session.flush()
    revoke_user_sessions(session, target.id, utcnow())


def change_own_password(session, payload, identity):
    lock_account_guard(session)
    user = current_locked_user(session, identity)
    current = payload.current_password.get_secret_value()
    replacement = payload.new_password.get_secret_value()
    if not verify_password(user.password_hash, current):
        raise unauthorized()
    if replacement == current:
        raise ServiceError(409, "password_reuse", "Choose a different password")
    user.password_hash = hash_password(replacement)
    session.flush()
    revoke_user_sessions(session, user.id, utcnow())
