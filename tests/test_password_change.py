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
from tests.test_auth import api, auth_engine, encoded_password, headers, login, PASSWORD

NEW_PASSWORD = "self-service example passphrase!"
RESET_PASSWORD = "administrator reset passphrase!"
PAYLOAD = {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
PATH = "/auth/change-password"


@pytest.mark.parametrize("username", ["admin", "auditor"])
def test_changes_own_password_and_revokes_every_session(api, username, caplog):
    c, engine, _ = api
    tokens = [login(c, username).json()["access_token"] for _ in range(2)]
    auth = headers(tokens[0])
    me = c.get("/auth/me", headers=auth).json()
    with Session(engine) as s, s.begin():
        now = utcnow()
        s.add(AuthSession(user_id=me["id"], token_hash="f" * 64,
                          created_at=now-timedelta(days=2), expires_at=now-timedelta(days=1)))
    response = c.post(PATH, headers=auth, json=PAYLOAD)
    assert response.status_code == 204 and response.content == b""
    assert all(c.get("/auth/me", headers=headers(token)).status_code == 401 for token in tokens)
    with Session(engine) as s:
        user = s.get(User, me["id"])
        assert user.role == me["role"] and user.is_active and user.full_name == me["full_name"]
        assert user.password_hash.startswith("$argon2id$") and verify_password(user.password_hash, NEW_PASSWORD)
        assert all(row.revoked_at is not None for row in
                   s.scalars(select(AuthSession).where(AuthSession.user_id == me["id"])))
    assert login(c, username).status_code == 401
    assert login(c, username, NEW_PASSWORD).status_code == 200
    assert all(secret not in caplog.text for secret in [PASSWORD, NEW_PASSWORD, *tokens])


@pytest.mark.parametrize("body,status", [
    ({"current_password": "incorrect"}, 401), ({"new_password": PASSWORD}, 409),
    ({"new_password": "short"}, 422), ({"new_password": " " * 20}, 422),
    ({"new_password": "x" * 129}, 422), ({"new_password": None}, 422),
    ({"current_password": ""}, 422), ({"current_password": "x" * 129}, 422),
    ({"new_password": 123}, 422), ({"user_id": 1}, 422), ({"role": "ADMIN"}, 422),
])
def test_rejected_changes_preserve_credentials(api, body, status):
    c, _, _ = api
    auth = headers(login(c).json()["access_token"])
    response = c.post(PATH, headers=auth, json=PAYLOAD | body)
    assert response.status_code == status
    assert PASSWORD not in response.text and NEW_PASSWORD not in response.text
    assert c.get("/auth/me", headers=auth).status_code == 200
    assert login(c).status_code == 200


@pytest.mark.parametrize("field", ["current_password", "new_password"])
def test_required_fields(api, field):
    c, _, _ = api
    auth = headers(login(c).json()["access_token"])
    body = dict(PAYLOAD)
    del body[field]
    assert c.post(PATH, headers=auth, json=body).status_code == 422


@pytest.mark.parametrize("state", ["missing", "disabled", "revoked"])
def test_requires_current_active_session(api, state):
    c, engine, _ = api
    auth = {}
    if state != "missing":
        auth = headers(login(c).json()["access_token"])
        me = c.get("/auth/me", headers=auth).json()
        if state == "disabled":
            with Session(engine) as s, s.begin():
                s.get(User, me["id"]).is_active = False
        else:
            assert c.post("/auth/logout", headers=auth).status_code == 204
    assert c.post(PATH, headers=auth, json=PAYLOAD).status_code == 401


@pytest.mark.parametrize("failure", ["password_write", "revoke", "commit"])
def test_failure_rolls_back_password_and_sessions(api, failure):
    c, engine, _ = api
    auth = headers(login(c).json()["access_token"])
    me = c.get("/auth/me", headers=auth).json()
    with Session(engine) as s:
        old_hash = s.get(User, me["id"]).password_hash
    def fail(*args):
        raise SQLAlchemyError("private database detail")
    def fail_revoke(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE auth_sessions"):
            fail()
    obj, name, callback = ((User, "before_update", fail) if failure == "password_write" else
                          (engine, "before_cursor_execute", fail_revoke) if failure == "revoke" else
                          (Session, "before_commit", fail))
    event.listen(obj, name, callback)
    try:
        response = c.post(PATH, headers=auth, json=PAYLOAD)
        assert response.status_code == 503
        assert all(value not in response.text for value in [PASSWORD, NEW_PASSWORD, old_hash, "private"])
    finally:
        event.remove(obj, name, callback)
    with Session(engine) as s:
        assert s.get(User, me["id"]).password_hash == old_hash
        assert all(row.revoked_at is None for row in
                   s.scalars(select(AuthSession).where(AuthSession.user_id == me["id"])))
    assert c.get("/auth/me", headers=auth).status_code == 200
    assert login(c).status_code == 200


@pytest.mark.parametrize("first", ["login", "change"])
def test_concurrent_login_and_change(api, monkeypatch, first):
    c, engine, _ = api
    auth = headers(login(c).json()["access_token"])
    me = c.get("/auth/me", headers=auth).json()
    login_locked, change_locked, login_attempted, change_attempted = (Event() for _ in range(4))
    original_find, original_guard = AuthRepository.find_user, user_service.lock_account_guard
    def find(repo, username):
        if username == "auditor":
            login_attempted.set()
        result = original_find(repo, username)
        if username == "auditor" and first == "login":
            login_locked.set()
            assert change_attempted.wait(10)
        return result
    def guard(session):
        change_attempted.set()
        return original_guard(session)
    def pause_change(mapper, connection, user):
        if user.id == me["id"] and inspect(user).attrs.password_hash.history.has_changes():
            change_locked.set()
            if first == "change":
                assert login_attempted.wait(10)
    monkeypatch.setattr(AuthRepository, "find_user", find)
    monkeypatch.setattr(user_service, "lock_account_guard", guard)
    event.listen(User, "before_update", pause_change)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            if first == "login":
                login_future = pool.submit(login, c)
                assert login_locked.wait(10)
                change_future = pool.submit(c.post, PATH, headers=auth, json=PAYLOAD)
            else:
                change_future = pool.submit(c.post, PATH, headers=auth, json=PAYLOAD)
                assert change_locked.wait(10)
                login_future = pool.submit(login, c)
            changed, logged_in = change_future.result(timeout=20), login_future.result(timeout=20)
    finally:
        event.remove(User, "before_update", pause_change)
    assert changed.status_code == 204
    assert logged_in.status_code == (200 if first == "login" else 401)
    if first == "login":
        assert c.get("/auth/me", headers=headers(logged_in.json()["access_token"])).status_code == 401
    with Session(engine) as s:
        assert all(row.revoked_at is not None for row in
                   s.scalars(select(AuthSession).where(AuthSession.user_id == me["id"])))
    monkeypatch.setattr(AuthRepository, "find_user", original_find)
    assert login(c).status_code == 401
    assert login(c, password=NEW_PASSWORD).status_code == 200


@pytest.mark.parametrize("first", ["change", "reset"])
def test_concurrent_admin_reset_and_change(api, monkeypatch, first):
    c, engine, _ = api
    admin = headers(login(c, "admin").json()["access_token"])
    auth = headers(login(c).json()["access_token"])
    me = c.get("/auth/me", headers=auth).json()
    first_locked, contender_attempted = Event(), Event()
    original_guard = user_service.lock_account_guard
    def guard(session):
        if first_locked.is_set():
            contender_attempted.set()
        return original_guard(session)
    def pause_first(mapper, connection, user):
        if (user.id == me["id"] and inspect(user).attrs.password_hash.history.has_changes()
                and not first_locked.is_set()):
            first_locked.set()
            assert contender_attempted.wait(10)
    monkeypatch.setattr(user_service, "lock_account_guard", guard)
    event.listen(User, "before_update", pause_first)
    def change():
        return c.post(PATH, headers=auth, json=PAYLOAD)
    def reset():
        return c.post(f"/users/{me['id']}/reset-password", headers=admin,
                      json={"admin_password": PASSWORD, "new_password": RESET_PASSWORD})
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            leading = pool.submit(change if first == "change" else reset)
            assert first_locked.wait(10)
            trailing = pool.submit(reset if first == "change" else change)
            lead_response, trail_response = leading.result(timeout=20), trailing.result(timeout=20)
    finally:
        event.remove(User, "before_update", pause_first)
    assert lead_response.status_code == 204
    assert trail_response.status_code == (204 if first == "change" else 401)
    assert c.get("/auth/me", headers=auth).status_code == 401
    with Session(engine) as s:
        assert all(row.revoked_at is not None for row in
                   s.scalars(select(AuthSession).where(AuthSession.user_id == me["id"])))
    assert login(c, password=NEW_PASSWORD).status_code == 401
    assert login(c, password=RESET_PASSWORD).status_code == 200


def test_change_preserves_audit_identity_and_history(api):
    c, _, _ = api
    auth = headers(login(c).json()["access_token"])
    record = c.post("/audits", headers=auth, json={"driver_name": "Example", "station": "Example",
                    "audit_date": "2026-10-26", "plate_number": "EXAMPLE"}).json()
    path = f"/audits/{record['id']}"
    history = c.get(path + "/history", headers=auth).json()
    assert c.post(PATH, headers=auth, json=PAYLOAD).status_code == 204
    replacement = headers(login(c, password=NEW_PASSWORD).json()["access_token"])
    assert c.get(path, headers=replacement).json() == record
    assert c.get(path + "/history", headers=replacement).json() == history
