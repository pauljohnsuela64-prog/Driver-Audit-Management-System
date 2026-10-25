"""Password hashes and opaque bearer credentials. Never log inputs."""
import hashlib
import re
import secrets
from threading import BoundedSemaphore

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID)
_HASH_SLOTS = BoundedSemaphore(4)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")


def hash_password(password: str) -> str:
    if not 15 <= len(password) <= 128:
        raise ValueError("Password must contain 15 to 128 characters")
    with _HASH_SLOTS:
        return HASHER.hash(password)


# Unknown usernames still perform one real Argon2 verification.
DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def verify_password(encoded: str, password: str) -> bool:
    if not 1 <= len(password) <= 128:
        return False
    try:
        with _HASH_SLOTS:
            return HASHER.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def refresh_password_hash(encoded: str, verified_password: str) -> str:
    """Call only after successful verification; preserve legacy password lengths."""
    if not HASHER.check_needs_rehash(encoded):
        return encoded
    with _HASH_SLOTS:
        return HASHER.hash(verified_password)
