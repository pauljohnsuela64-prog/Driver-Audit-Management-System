from datetime import timedelta

from backend.core.database import utcnow
from backend.core.errors import unauthorized
from backend.core.security import DUMMY_HASH, new_token, refresh_password_hash, token_hash, verify_password
from backend.models import AuthSession
from backend.repositories.auth import AuthRepository

SESSION_LIFETIME = timedelta(hours=8)


class AuthService:
    def __init__(self, repository: AuthRepository):
        self.repository = repository

    def login(self, username: str, password: str):
        user = self.repository.find_user(username)
        valid = verify_password(user.password_hash if user else DUMMY_HASH, password)
        if not user or not valid or not user.is_active or user.role not in {"ADMIN", "AUDITOR"}:
            raise unauthorized()
        user.password_hash = refresh_password_hash(user.password_hash, password)
        now = utcnow()
        token = new_token()
        record = AuthSession(user_id=user.id, token_hash=token_hash(token),
                             created_at=now, expires_at=now + SESSION_LIFETIME)
        self.repository.add_session(record)
        return token, record.expires_at

    def authenticate(self, token: str):
        pair = self.repository.find_session(token_hash(token))
        if not pair:
            raise unauthorized()
        record, user = pair
        if (record.revoked_at is not None or record.expires_at <= utcnow()
                or not user.is_active or user.role not in {"ADMIN", "AUDITOR"}):
            raise unauthorized()
        return record, user

    def logout(self, record: AuthSession):
        self.repository.revoke(record.id, utcnow())
