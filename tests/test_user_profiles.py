import pytest
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
