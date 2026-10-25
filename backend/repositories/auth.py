from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.models import AuthSession, User


class AuthRepository:
    def __init__(self, session: Session):
        self.session = session

    def find_user(self, username: str):
        return self.session.scalar(select(User).where(User.username == username).with_for_update())

    def find_session(self, digest: str):
        return self.session.execute(
            select(AuthSession, User).join(User, User.id == AuthSession.user_id)
            .where(AuthSession.token_hash == digest)
        ).first()

    def add_session(self, record: AuthSession):
        self.session.add(record)
        self.session.flush()

    def revoke(self, session_id: int, now):
        self.session.execute(update(AuthSession).where(
            AuthSession.id == session_id, AuthSession.revoked_at.is_(None)
        ).values(revoked_at=now))
