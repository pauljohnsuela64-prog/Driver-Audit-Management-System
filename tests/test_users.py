from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.core.security import verify_password
from backend.models import User
from tests.test_auth import api, auth_engine, encoded_password, headers, login
from tests.test_user_schemas import PAYLOAD

SAFE_FIELDS = {"id", "username", "full_name", "role", "is_active"}


@pytest.fixture
def accounts(api):
    c, engine, _ = api
    return c, engine, headers(login(c,"admin").json()["access_token"])


@pytest.mark.parametrize("role", ["ADMIN","AUDITOR"])
def test_create_hash_and_detail(accounts, role):
    c, engine, auth = accounts
    response = c.post("/users",headers=auth,json=PAYLOAD | {"role":role})
    assert response.status_code == 201
    account = response.json()
    assert set(account) == SAFE_FIELDS and account["is_active"] is True
    assert account["role"] == role
    with Session(engine) as s:
        user = s.get(User,account["id"])
        assert user.password_hash.startswith("$argon2id$")
        assert verify_password(user.password_hash,PAYLOAD["password"])
        assert user.password_hash not in response.text and PAYLOAD["password"] not in response.text
    assert c.get(f"/users/{account['id']}",headers=auth).json() == account
    assert login(c,PAYLOAD["username"],PAYLOAD["password"]).status_code == 200
    assert c.get("/users/999999",headers=auth).status_code == 404


@pytest.mark.parametrize("identity,status", [(None,401),("auditor",403)])
def test_all_routes_protected(api, identity, status):
    c, engine, _ = api
    auth = {} if identity is None else headers(login(c,identity).json()["access_token"])
    for method,path,body in [("post","/users",PAYLOAD),("get","/users",None),("get","/users/1",None)]:
        assert c.request(method,path,headers=auth,json=body).status_code == status
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(User)) == 3


def test_duplicates_and_concurrent_creation(accounts):
    c, engine, auth = accounts
    barrier = Barrier(2)
    def overlap(connection,cursor,statement,parameters,context,executemany):
        if statement.startswith("INSERT INTO users"):
            barrier.wait(timeout=10)
    def create(_):
        return c.post("/users",headers=auth,json=PAYLOAD)
    event.listen(engine,"before_cursor_execute",overlap)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(create,range(2)))
    finally:
        event.remove(engine,"before_cursor_execute",overlap)
    assert sorted(r.status_code for r in responses) == [201,409]
    assert c.post("/users",headers=auth,json=PAYLOAD | {"username":" employee "}).status_code == 409
    if engine.dialect.name == "mysql":
        assert c.post("/users",headers=auth,json=PAYLOAD | {"username":"EMPLOYEE"}).status_code == 409
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(User)) == 4


def test_listing_search_pagination(accounts):
    c, _, auth = accounts
    assert c.post("/users",headers=auth,json=PAYLOAD | {"full_name":"Example% Employee"}).status_code == 201
    page = c.get("/users?page_size=2",headers=auth).json()
    next_page = c.get("/users?page_size=2&page=2",headers=auth).json()
    assert page["total"] == 4 and len(page["items"]) == 2
    assert {u["id"] for u in page["items"]}.isdisjoint({u["id"] for u in next_page["items"]})
    assert all(set(u)==SAFE_FIELDS for u in page["items"]+next_page["items"])
    assert any(not u["is_active"] for u in next_page["items"])
    for search,count in [("employee",1),("Example%",1),("%",1),("_",0),("' OR 1=1 --",0)]:
        result = c.get("/users",headers=auth,params={"search":search})
        assert result.status_code == 200 and result.json()["total"] == count
    for query in ["page=0","page_size=101","page=10001","search=", "search=%20%20"]:
        assert c.get("/users?"+query,headers=auth).status_code == 422


@pytest.mark.parametrize("field,value", [("password","short"),("password"," "*20),
    ("username"," "),("full_name",None),("role","OWNER"),("is_active",False),
    ("password_hash","private marker"),("id",123)])
def test_invalid_api_input(accounts, field, value):
    c, _, auth = accounts
    response = c.post("/users",headers=auth,json=PAYLOAD | {field:value})
    assert response.status_code == 422
    assert PAYLOAD["password"] not in response.text and "private marker" not in response.text


@pytest.mark.parametrize("failure", ["insert","commit","read"])
def test_database_errors_sanitized_and_rolled_back(accounts, failure):
    c, engine, auth = accounts
    def fail(*args):
        raise SQLAlchemyError("private connection or password detail")
    def fail_read(connection,cursor,statement,parameters,context,executemany):
        if "FROM users" in statement:
            fail()
    target, name, handler = ((User,"before_insert",fail) if failure == "insert" else
                             (Session,"before_commit",fail) if failure == "commit" else
                             (engine,"before_cursor_execute",fail_read))
    event.listen(target,name,handler)
    try:
        response = c.get("/users",headers=auth) if failure == "read" else c.post("/users",headers=auth,json=PAYLOAD)
        assert response.status_code == 503
        assert "private" not in response.text and PAYLOAD["password"] not in response.text
    finally:
        event.remove(target,name,handler)
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(User)) == 3
