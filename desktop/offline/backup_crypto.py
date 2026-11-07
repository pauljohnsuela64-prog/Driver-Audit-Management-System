"""Fixed, authenticated backup envelope. No password/key persistence or logging."""
import os
import struct
import unicodedata

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from .models import OfflineError

MAX_PAYLOAD = 64 * 1024 * 1024
HEADER = struct.Struct('<8sHHBBBBIIII16s12sQQI16s')
HEADER_SIZE = HEADER.size
PLATFORMS = {'windows': 1, 'android': 2}
UNLOCK_MESSAGE = 'Cannot unlock this backup. Check the password or use another backup. Nothing was restored.'


def _format_error():
    raise OfflineError('backup_format', 'This backup is unsupported, incomplete or exceeds safe limits. Nothing was restored.')


def _password(value):
    try:
        if (not isinstance(value, str) or not 15 <= len(value) <= 128 or value.isspace()
                or any(unicodedata.category(c) == 'Cc' for c in value)):
            raise ValueError()
        raw = value.encode('utf-8', errors='strict')
        if len(raw) > 512:
            raise ValueError()
        return raw
    except (ValueError, UnicodeError):
        raise OfflineError('backup_password', 'Use a nonblank backup passphrase of 15–128 characters without control characters.') from None


def _derive_key(password, salt):
    return Argon2id(salt=salt, length=32, iterations=2, lanes=1, memory_cost=19456).derive(password)


def seal_backup(payload, password, *, platform):
    if platform not in PLATFORMS or not isinstance(payload, bytes) or len(payload) > MAX_PAYLOAD:
        _format_error()
    secret = _password(password)
    salt, nonce = os.urandom(16), os.urandom(12)
    header = HEADER.pack(b'BHLIBAK\0', 1, 96, PLATFORMS[platform], 1, 1, 0, 2,
                         19456, 2, 1, salt, nonce, len(payload), len(payload)+16, 1, bytes(16))
    key = _derive_key(secret, salt)
    try:
        return header + AESGCM(key).encrypt(nonce, payload, header)
    finally:
        # Immutable runtime/OS copies cannot be guaranteed erased.
        del key, secret


def open_backup(raw, password, *, platform):
    if platform not in PLATFORMS or not isinstance(raw, bytes) or not 112 <= len(raw) <= MAX_PAYLOAD + 112:
        _format_error()
    fields = HEADER.unpack_from(raw)
    magic, version, length, source, cipher, kdf, reserved, schema, memory, passes, lanes, salt, nonce, plain, encrypted, payload, tail = fields
    if (magic != b'BHLIBAK\0' or (version, length, cipher, kdf, reserved, schema, memory, passes, lanes, payload) !=
            (1, 96, 1, 1, 0, 2, 19456, 2, 1, 1) or source not in PLATFORMS.values()
            or tail != bytes(16) or plain > MAX_PAYLOAD or encrypted != plain + 16 or len(raw) != 96 + encrypted):
        _format_error()
    secret = _password(password)
    key = _derive_key(secret, salt)
    try:
        try:
            result = AESGCM(key).decrypt(nonce, raw[96:], raw[:96])
        except InvalidTag:
            raise OfflineError('backup_unlock', UNLOCK_MESSAGE) from None
        if source != PLATFORMS[platform]:
            raise OfflineError('backup_platform', 'Full backups can only be restored on the same offline platform. Use Transfer audits to copy between platforms.')
        return result
    finally:
        del key, secret
