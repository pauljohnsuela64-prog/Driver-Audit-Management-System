import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.core.security import verify_password
from backend.models import AuthSession, User
from backend.schemas.users import PasswordResetRequest
from tests.test_auth import api, auth_engine, encoded_password, headers, login, PASSWORD
from tests.test_users import accounts

NEW_PASSWORD = "new example-only passphrase!"
PAYLOAD = {"admin_password":PASSWORD,"new_password":NEW_PASSWORD}


def target(c, admin, username="auditor"):
    return next(u for u in c.get("/users",headers=admin).json()["items"] if u["username"] == username)


def test_reset_reauthentication_hash_and_all_sessions(accounts, caplog):
    c, engine, admin = accounts
    user=target(c,admin)
    sessions=[headers(login(c).json()["access_token"]) for _ in range(2)]
    response=c.post(f"/users/{user['id']}/reset-password",headers=admin,json=PAYLOAD)
    assert response.status_code == 204 and response.content == b""
    assert all(c.get("/auth/me",headers=h).status_code == 401 for h in sessions)
    assert login(c).status_code == 401
    assert login(c,password=NEW_PASSWORD).status_code == 200
    with Session(engine) as s:
        stored=s.get(User,user["id"])
        assert stored.password_hash.startswith("$argon2id$") and verify_password(stored.password_hash,NEW_PASSWORD)
        assert stored.role == user["role"] and stored.is_active == user["is_active"]
        old_sessions=s.scalars(select(AuthSession).where(AuthSession.user_id == user["id"]).order_by(AuthSession.id)).all()
        assert all(row.revoked_at is not None for row in old_sessions[:-1])
        assert stored.password_hash not in response.text
    assert PASSWORD not in caplog.text and NEW_PASSWORD not in caplog.text
    schema=PasswordResetRequest(**PAYLOAD)
    assert PASSWORD not in repr(schema) and NEW_PASSWORD not in repr(schema)


@pytest.mark.parametrize("identity,status", [(None,401),("auditor",403)])
def test_requires_admin(api, identity, status):
    c, _, _=api
    auth={} if identity is None else headers(login(c,identity).json()["access_token"])
    assert c.post("/users/2/reset-password",headers=auth,json=PAYLOAD).status_code == status


def test_wrong_admin_password_self_and_missing(accounts):
    c, _, admin=accounts
    user=target(c,admin)
    path=f"/users/{user['id']}/reset-password"
    assert c.post(path,headers=admin,json=PAYLOAD | {"admin_password":"incorrect"}).status_code == 401
    assert login(c).status_code == 200
    me=c.get("/auth/me",headers=admin).json()
    assert c.post(f"/users/{me['id']}/reset-password",headers=admin,json=PAYLOAD).status_code == 409
    assert c.post("/users/999999/reset-password",headers=admin,json=PAYLOAD).status_code == 404


@pytest.mark.parametrize("change", [{"new_password":"short"},{"new_password":" "*20},
    {"new_password":"x"*129},{"new_password":None},{"admin_password":""},
    {"admin_password":"x"*129},{"admin_password":None},{"role":"ADMIN"},
    {"password_hash":"forged"},{"new_password":123}])
def test_invalid_payload(accounts, change):
    c, _, admin=accounts
    response=c.post("/users/2/reset-password",headers=admin,json=PAYLOAD | change)
    assert response.status_code == 422 and NEW_PASSWORD not in response.text and PASSWORD not in response.text
