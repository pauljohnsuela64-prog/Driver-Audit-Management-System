from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from backend.models import User
from tests.test_auth import api, auth_engine, encoded_password, headers, login
from tests.test_users import accounts, SAFE_FIELDS


def test_partial_updates_and_self_edit(accounts):
    c, _, auth = accounts
    me = c.get("/auth/me",headers=auth).json()
    path = f"/users/{me['id']}"
    response = c.patch(path,headers=auth,json={"username":" renamed.admin "})
    assert response.status_code == 200 and set(response.json()) == SAFE_FIELDS
    assert response.json()["username"] == "renamed.admin" and response.json()["full_name"] == me["full_name"]
    response = c.patch(path,headers=auth,json={"full_name":" New Name "})
    assert response.status_code == 200 and response.json()["full_name"] == "New Name"
    assert response.json()["username"] == "renamed.admin" and response.json()["id"] == me["id"]
    assert c.get("/auth/me",headers=auth).json()["full_name"] == "New Name"
    assert login(c,"renamed.admin").status_code == 200
    assert c.patch(path,headers=auth,json={"username":"renamed.admin"}).status_code == 200
    assert c.patch("/users/999999",headers=auth,json={"full_name":"Name"}).status_code == 404


@pytest.mark.parametrize("body", [{},{"username":None},{"full_name":" "},{"username":" "},
    {"role":"ADMIN"},{"is_active":False},{"password_hash":"forged"},{"id":2},
    {"created_at":"2026-01-01"},{"password":"secret"},{"username":"x"*101},
    {"full_name":"x"*201},{"full_name":None},{"username":42}])
def test_invalid_profile_payload(accounts, body):
    c, _, auth = accounts
    user_id = c.get("/auth/me",headers=auth).json()["id"]
    assert c.patch(f"/users/{user_id}",headers=auth,json=body).status_code == 422


@pytest.mark.parametrize("identity,status", [(None,401),("auditor",403)])
def test_edit_requires_admin(api, identity, status):
    c, _, _ = api
    auth = {} if identity is None else headers(login(c,identity).json()["access_token"])
    assert c.patch("/users/1",headers=auth,json={"full_name":"Forbidden"}).status_code == status


def test_edit_employee_preserves_audit_identity(accounts):
    c, engine, admin = accounts
    auditor = headers(login(c).json()["access_token"])
    me = c.get("/auth/me",headers=auditor).json()
    audit = c.post("/audits",headers=auditor,json={"driver_name":"Example", "audit_date":"2026-10-26",
                  "station":"Example", "plate_number":"EXAMPLE"}).json()
    with Session(engine) as s:
        before_hash = s.get(User,me["id"]).password_hash
    response = c.patch(f"/users/{me['id']}",headers=admin,
                       json={"username":"renamed.employee","full_name":"Renamed Employee"})
    assert response.status_code == 200 and response.json()["id"] == me["id"]
    assert response.json()["role"] == "AUDITOR" and response.json()["is_active"] is True
    with Session(engine) as s:
        assert s.get(User,me["id"]).password_hash == before_hash
    assert c.get("/auth/me",headers=auditor).json()["full_name"] == "Renamed Employee"
    assert login(c,"renamed.employee").status_code == 200
    assert login(c,"auditor").status_code == 401
    stored = c.get(f"/audits/{audit['id']}",headers=auditor).json()
    history = c.get(f"/audits/{audit['id']}/history",headers=auditor).json()["items"]
    assert stored["audited_by_name"] == audit["audited_by_name"] == "auditor"
    assert stored["audited_by_user_id"] == me["id"]
    assert history[0]["after_data"]["audited_by_name"] == "auditor"
    assert c.patch(f"/audits/{audit['id']}",headers=auditor | {"If-Match":'"1"'},
                   json={"remarks":"Still owned"}).status_code == 200


def test_duplicate_username_rolls_back_all_fields(accounts):
    c, engine, auth = accounts
    me = c.get("/auth/me",headers=auth).json()
    for username in (["auditor","AUDITOR"] if engine.dialect.name == "mysql" else ["auditor"]):
        response = c.patch(f"/users/{me['id']}",headers=auth,
                           json={"username":username,"full_name":"Must roll back"})
        assert response.status_code == 409
        current = c.get(f"/users/{me['id']}",headers=auth).json()
        assert current["username"] == me["username"] and current["full_name"] == me["full_name"]


@pytest.mark.parametrize("scenario", ["different_fields","duplicate_username"])
def test_concurrent_profile_edits(accounts, scenario):
    c, engine, auth = accounts
    users = c.get("/users",headers=auth).json()["items"]
    first, second = users[0], users[1]
    barrier = Barrier(2)
    def overlap(connection,cursor,statement,parameters,context,executemany):
        if statement == "BEGIN IMMEDIATE" or ("SELECT users.id" in statement
                and "ORDER BY users.id" in statement and "FOR UPDATE" in statement):
            barrier.wait(timeout=10)
    def request(i):
        target = first if scenario == "different_fields" or i == 0 else second
        payload = ({"username":"concurrent.name"} if i == 0 else {"full_name":"Concurrent Name"}) if scenario == "different_fields" else {"username":"contended.name"}
        return c.patch(f"/users/{target['id']}",headers=auth,json=payload)
    event.listen(engine,"before_cursor_execute",overlap)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(request,range(2)))
    finally:
        event.remove(engine,"before_cursor_execute",overlap)
    assert sorted(r.status_code for r in responses) == ([200,200] if scenario == "different_fields" else [200,409])
    with Session(engine) as s:
        if scenario == "different_fields":
            user=s.get(User,first["id"])
            assert user.username == "concurrent.name" and user.full_name == "Concurrent Name"
        else:
            assert len(s.scalars(select(User).where(User.username == "contended.name")).all()) == 1


@pytest.mark.parametrize("failure", ["update","commit"])
def test_profile_database_failure_rolls_back(accounts, failure):
    c, engine, auth = accounts
    me = c.get("/auth/me",headers=auth).json()
    def fail(*args):
        raise SQLAlchemyError("private database detail")
    def fail_update(connection,cursor,statement,parameters,context,executemany):
        if statement.startswith("UPDATE users"):
            fail()
    target,name,handler = (engine,"before_cursor_execute",fail_update) if failure == "update" else (Session,"before_commit",fail)
    event.listen(target,name,handler)
    try:
        response=c.patch(f"/users/{me['id']}",headers=auth,json={"full_name":"Not committed"})
        assert response.status_code == 503 and "private" not in response.text
    finally:
        event.remove(target,name,handler)
    with Session(engine) as s:
        assert s.get(User,me["id"]).full_name == me["full_name"]


@pytest.mark.parametrize("change,status", [("role",403),("disabled",401),("logout",401)])
def test_current_session_permissions_still_enforced(accounts, change, status):
    c, engine, auth = accounts
    me=c.get("/auth/me",headers=auth).json()
    if change == "logout":
        assert c.post("/auth/logout",headers=auth).status_code == 204
    else:
        with Session(engine) as s,s.begin():
            user=s.get(User,me["id"])
            if change == "role":user.role="AUDITOR"
            else:user.is_active=False
    assert c.patch(f"/users/{me['id']}",headers=auth,json={"full_name":"Denied"}).status_code == status
