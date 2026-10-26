from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from sqlalchemy import event, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from backend.core.database import utcnow
from backend.core.security import verify_password
from backend.models import AuthSession, User
from backend.repositories.auth import AuthRepository
import backend.services.users as user_service
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


@pytest.mark.parametrize("field", ["admin_password", "new_password"])
def test_required_fields(accounts, field):
    c, _, admin = accounts
    payload = dict(PAYLOAD)
    del payload[field]
    assert c.post("/users/2/reset-password", headers=admin, json=payload).status_code == 422


def test_disabled_reset_revokes_expired_sessions(accounts):
    c, engine, admin = accounts
    user = target(c, admin, "disabled")
    with Session(engine) as s, s.begin():
        now = utcnow()
        s.add(AuthSession(user_id=user["id"], token_hash="e" * 64,
                          created_at=now-timedelta(days=2), expires_at=now-timedelta(days=1)))
    path = f"/users/{user['id']}"
    assert c.post(path + "/reset-password", headers=admin, json=PAYLOAD).status_code == 204
    with Session(engine) as s:
        stored = s.get(User, user["id"])
        assert stored.role == user["role"] and not stored.is_active
        assert s.scalar(select(AuthSession).where(AuthSession.user_id == user["id"])).revoked_at is not None
    assert login(c, "disabled", NEW_PASSWORD).status_code == 401
    assert c.patch(path + "/access", headers=admin, json={"is_active": True}).status_code == 200
    assert login(c, "disabled", NEW_PASSWORD).status_code == 200
    assert login(c, "disabled", PASSWORD).status_code == 401


@pytest.mark.parametrize("failure", ["password_write", "revoke", "commit"])
def test_reset_failure_rolls_back(accounts, failure):
    c, engine, admin = accounts
    user = target(c, admin)
    token = headers(login(c).json()["access_token"])
    with Session(engine) as s:
        old_hash = s.get(User, user["id"]).password_hash
    def fail(*args):
        raise SQLAlchemyError("private credential detail")
    def fail_revoke(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE auth_sessions"):
            fail()
    obj, name, callback = ((User, "before_update", fail) if failure == "password_write" else
                          (engine, "before_cursor_execute", fail_revoke) if failure == "revoke" else
                          (Session, "before_commit", fail))
    event.listen(obj, name, callback)
    try:
        response = c.post(f"/users/{user['id']}/reset-password", headers=admin, json=PAYLOAD)
        assert response.status_code == 503
        assert all(value not in response.text for value in ["private", NEW_PASSWORD, PASSWORD, old_hash])
    finally:
        event.remove(obj, name, callback)
    with Session(engine) as s:
        assert s.get(User, user["id"]).password_hash == old_hash
        assert all(row.revoked_at is None for row in
                   s.scalars(select(AuthSession).where(AuthSession.user_id == user["id"])))
    assert c.get("/auth/me", headers=token).status_code == 200
    assert login(c).status_code == 200
    assert login(c, password=NEW_PASSWORD).status_code == 401


@pytest.mark.parametrize("first", ["login", "reset"])
def test_concurrent_login_and_reset(accounts, monkeypatch, first):
    c, engine, admin = accounts
    user = target(c, admin)
    login_locked, reset_locked, login_attempted, reset_attempted = (Event() for _ in range(4))
    original_find = AuthRepository.find_user
    original_guard = user_service.lock_account_guard
    def find(repo, username):
        if username == "auditor":
            login_attempted.set()
        result = original_find(repo, username)
        if username == "auditor" and first == "login":
            login_locked.set()
            assert reset_attempted.wait(10)
        return result
    def guard(session):
        reset_attempted.set()
        return original_guard(session)
    def pause_reset(mapper, connection, record):
        if record.id == user["id"] and inspect(record).attrs.password_hash.history.has_changes():
            reset_locked.set()
            if first == "reset":
                assert login_attempted.wait(10)
    monkeypatch.setattr(AuthRepository, "find_user", find)
    monkeypatch.setattr(user_service, "lock_account_guard", guard)
    event.listen(User, "before_update", pause_reset)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            if first == "login":
                login_future = pool.submit(login, c)
                assert login_locked.wait(10)
                reset_future = pool.submit(c.post, f"/users/{user['id']}/reset-password",
                                           headers=admin, json=PAYLOAD)
            else:
                reset_future = pool.submit(c.post, f"/users/{user['id']}/reset-password",
                                           headers=admin, json=PAYLOAD)
                assert reset_locked.wait(10)
                login_future = pool.submit(login, c)
            reset_response = reset_future.result(timeout=20)
            login_response = login_future.result(timeout=20)
    finally:
        event.remove(User, "before_update", pause_reset)
    assert reset_response.status_code == 204
    assert login_response.status_code == (200 if first == "login" else 401)
    if first == "login":
        assert c.get("/auth/me", headers=headers(login_response.json()["access_token"])).status_code == 401
    with Session(engine) as s:
        assert all(row.revoked_at is not None for row in
                   s.scalars(select(AuthSession).where(AuthSession.user_id == user["id"])))
    monkeypatch.setattr(AuthRepository, "find_user", original_find)
    assert login(c).status_code == 401
    assert login(c, password=NEW_PASSWORD).status_code == 200
