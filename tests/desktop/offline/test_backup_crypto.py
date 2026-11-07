"""Real fixed-suite encryption, never production secrets."""
import struct
import pytest
from desktop.offline.models import OfflineError
from desktop.offline.backup_crypto import seal_backup, open_backup, HEADER_SIZE, MAX_PAYLOAD

PASSWORD = 'Fictional passphrase 2026!'

def test_real_crypto_roundtrip_fresh_randomness_and_platform_binding():
    payload = b'fictional complete-state payload'
    first = seal_backup(payload, PASSWORD, platform='windows')
    second = seal_backup(payload, PASSWORD, platform='windows')
    assert HEADER_SIZE == 96 and len(first) == len(payload) + 112
    assert first[:8] == b'BHLIBAK\0' and first != second
    assert open_backup(first, PASSWORD, platform='windows') == payload
    with pytest.raises(OfflineError): open_backup(first, PASSWORD, platform='android')

def test_wrong_password_and_authenticated_tamper_are_sanitized():
    raw = seal_backup(b'Fictional audit payload', PASSWORD, platform='android')
    for candidate, password in [(raw, 'Wrong fictional password'), (raw[:-1]+bytes([raw[-1]^1]), PASSWORD),
                                (raw[:32]+bytes([raw[32]^1])+raw[33:], PASSWORD)]:
        with pytest.raises(OfflineError) as caught:
            open_backup(candidate, password, platform='android')
        assert caught.value.code == 'backup_unlock'
        assert password not in str(caught.value) and 'audit payload' not in str(caught.value)

@pytest.mark.parametrize('offset,value', [(20,2**32-1),(24,0),(28,32),(76,2),(16,3)])
def test_hostile_header_rejected_before_kdf(monkeypatch,offset,value):
    from desktop.offline import backup_crypto
    raw = bytearray(seal_backup(b'fictional', PASSWORD, platform='windows'))
    struct.pack_into('<I',raw,offset,value)
    def forbidden(*args): pytest.fail('Hostile header reached KDF')
    monkeypatch.setattr(backup_crypto, '_derive_key', forbidden)
    with pytest.raises(OfflineError): open_backup(bytes(raw),PASSWORD,platform='windows')

@pytest.mark.parametrize('password',['short',' '*15,'x'*129,'x'*14+'\n','x'*14+'\ud800'])
def test_invalid_password_never_reaches_encryption(password):
    with pytest.raises(OfflineError): seal_backup(b'fixture',password,platform='windows')

def test_unicode_password_is_exact_and_trailing_bytes_rejected():
    password='架空のパスワード'+('é'*15)
    raw=seal_backup(b'fixture',password,platform='windows')
    assert open_backup(raw,password,platform='windows')==b'fixture'
    for changed in (raw+b'X',raw[:-1],b'',raw[:60]+(MAX_PAYLOAD+1).to_bytes(8,'little')+raw[68:]):
        with pytest.raises(OfflineError): open_backup(changed,password,platform='windows')

def test_actual_dart_fixture_decrypts_and_matches_python_canonical_payload():
    from pathlib import Path
    import hashlib
    folder=Path(__file__).resolve().parents[3]/'mobile/test/fixtures/backup'
    raw=(folder/'dart-android.bhlibackup').read_bytes()
    plain=open_backup(raw,PASSWORD,platform='android')
    assert hashlib.sha256(plain).digest()==hashlib.sha256((folder/'python-android-state.ndjson').read_bytes()).digest()
