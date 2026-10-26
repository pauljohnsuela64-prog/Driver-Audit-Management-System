import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.models import AuthSession, User
from tests.test_auth import api, auth_engine, encoded_password, headers, login
from tests.test_users import accounts, SAFE_FIELDS


def test_promote_demote_disable_reactivate_and_revoke(accounts):
    c, engine, admin = accounts
    token = login(c).json()["access_token"]
    auditor = headers(token)
    me = c.get("/auth/me",headers=auditor).json()
    path = f"/users/{me['id']}/access"
    for change in [{"role":"ADMIN"},{"role":"AUDITOR"},{"is_active":False},{"is_active":True}]:
        response = c.patch(path,headers=admin,json=change)
        assert response.status_code == 200 and set(response.json()) == SAFE_FIELDS
        assert all(response.json()[k] == v for k,v in change.items())
        assert c.get("/auth/me",headers=auditor).status_code == 401
        if change == {"is_active":False}:
            assert login(c).status_code == 401
        else:
            result = login(c)
            assert result.status_code == 200
            auditor = headers(result.json()["access_token"])
    with Session(engine) as s:
        sessions = s.scalars(select(AuthSession).where(AuthSession.user_id == me["id"]).order_by(AuthSession.id)).all()
        assert all(row.revoked_at is not None for row in sessions[:-1])
        assert sessions[-1].revoked_at is None


@pytest.mark.parametrize("identity,status", [(None,401),("auditor",403)])
def test_access_requires_admin(api, identity, status):
    c, _, _ = api
    auth = {} if identity is None else headers(login(c,identity).json()["access_token"])
    assert c.patch("/users/1/access",headers=auth,json={"role":"ADMIN"}).status_code == status


@pytest.mark.parametrize("body", [{"role":"AUDITOR"},{"is_active":False},{"role":"AUDITOR","is_active":False}])
def test_self_and_last_admin_protection(accounts, body):
    c, _, admin = accounts
    me = c.get("/auth/me",headers=admin).json()
    assert c.patch(f"/users/{me['id']}/access",headers=admin,json=body).status_code == 409
    assert c.get("/auth/me",headers=admin).json()["role"] == "ADMIN"
    assert sum(u["role"] == "ADMIN" and u["is_active"] for u in c.get("/users",headers=admin).json()["items"]) == 1


@pytest.mark.parametrize("body", [{},{"role":None},{"is_active":None},{"role":"admin"},
    {"role":"OWNER"},{"role":1},{"is_active":1},{"is_active":0},{"is_active":"false"},
    {"is_active":"true"},{"password":"secret"},{"full_name":"Name"},{"id":1},
    {"password_hash":"hash"},{"updated_at":"2026-10-26"}])
def test_invalid_access_payload(accounts, body):
    c, _, admin = accounts
    assert c.patch("/users/1/access",headers=admin,json=body).status_code == 422


def test_missing_account_and_noop_preserve_sessions(accounts):
    c, engine, admin = accounts
    me = c.get("/auth/me",headers=admin).json()
    assert c.patch("/users/999999/access",headers=admin,json={"role":"ADMIN"}).status_code == 404
    assert c.patch(f"/users/{me['id']}/access",headers=admin,json={"role":"ADMIN","is_active":True}).status_code == 200
    assert c.get("/auth/me",headers=admin).status_code == 200
