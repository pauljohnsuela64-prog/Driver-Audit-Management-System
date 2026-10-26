from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import Select
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


@pytest.mark.parametrize("scenario", ["cross_demote","cross_disable","same_target"])
def test_concurrent_access_safeguards(accounts, scenario):
    c, engine, admin = accounts
    first = c.get("/auth/me",headers=admin).json()
    second = c.post("/users",headers=admin,json={"username":"second.admin", "full_name":"Second Admin",
                    "role":"ADMIN","password":"second example passphrase"}).json()
    other = headers(login(c,"second.admin","second example passphrase").json()["access_token"])
    target = next(u for u in c.get("/users",headers=admin).json()["items"] if u["username"] == "auditor")
    barrier=Barrier(2)
    observed_reads=[]
    def overlap(connection,cursor,statement,parameters,context,executemany):
        compiled = context.compiled.statement if context.compiled is not None else None
        if isinstance(compiled, Select) and list(compiled.selected_columns.keys()) == ["role","is_active"]:
            observed_reads.append(True)
            barrier.wait(timeout=10)
    def request(i):
        auth = admin if i == 0 else other
        user_id = target["id"] if scenario == "same_target" else (second["id"] if i == 0 else first["id"])
        body = ({"role":"ADMIN"} if i == 0 else {"is_active":False}) if scenario == "same_target" else ({"role":"AUDITOR"} if scenario == "cross_demote" else {"is_active":False})
        return c.patch(f"/users/{user_id}/access",headers=auth,json=body)
    event.listen(engine,"after_cursor_execute",overlap)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(request,range(2)))
    finally:
        event.remove(engine,"after_cursor_execute",overlap)
    assert len(observed_reads) == 2
    codes=sorted(r.status_code for r in responses)
    assert codes == ([200,409] if scenario == "same_target" else [200,401])
    with Session(engine) as s:
        admins = s.scalars(select(User).where(User.role == "ADMIN",User.is_active.is_(True))).all()
        assert len(admins) >= 1
        if scenario != "same_target":
            assert len(admins) == 1


@pytest.mark.parametrize("failure", ["revoke","commit"])
def test_access_failure_rolls_back_user_and_sessions(accounts, failure):
    c, engine, admin = accounts
    auditor = headers(login(c).json()["access_token"])
    me = c.get("/auth/me",headers=auditor).json()
    def fail(*args):
        raise SQLAlchemyError("private credential detail")
    def fail_revoke(connection,cursor,statement,parameters,context,executemany):
        if statement.startswith("UPDATE auth_sessions"):
            fail()
    target,name,handler = (engine,"before_cursor_execute",fail_revoke) if failure == "revoke" else (Session,"before_commit",fail)
    event.listen(target,name,handler)
    try:
        response=c.patch(f"/users/{me['id']}/access",headers=admin,json={"role":"ADMIN","is_active":False})
        assert response.status_code == 503 and "private" not in response.text
    finally:
        event.remove(target,name,handler)
    with Session(engine) as s:
        user=s.get(User,me["id"])
        assert user.role == "AUDITOR" and user.is_active is True
        sessions=s.scalars(select(AuthSession).where(AuthSession.user_id == me["id"])).all()
        assert all(row.revoked_at is None for row in sessions)
    assert c.get("/auth/me",headers=auditor).status_code == 200


def test_access_changes_preserve_attribution_and_revoke_all_live_sessions(accounts):
    c, engine, admin = accounts
    tokens=[headers(login(c).json()["access_token"]) for _ in range(2)]
    me=c.get("/auth/me",headers=tokens[0]).json()
    audit=c.post("/audits",headers=tokens[0],json={"driver_name":"Example", "station":"Example",
                "audit_date":"2026-10-26","plate_number":"EXAMPLE"}).json()
    before=c.get(f"/audits/{audit['id']}/history",headers=admin).json()
    path=f"/users/{me['id']}/access"
    assert c.patch(path,headers=admin,json={"role":"ADMIN","is_active":False}).status_code == 200
    assert all(c.get("/auth/me",headers=h).status_code == 401 for h in tokens)
    assert login(c).status_code == 401
    assert c.patch(path,headers=admin,json={"is_active":True}).status_code == 200
    assert all(c.get("/auth/me",headers=h).status_code == 401 for h in tokens)
    assert login(c).status_code == 200
    assert c.get(f"/audits/{audit['id']}",headers=admin).json() == audit
    assert c.get(f"/audits/{audit['id']}/history",headers=admin).json() == before
