import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from backend.models import AdminActivityEvent, User
from tests.constraint_support import constraint_violation
from tests.test_auth import api, auth_engine, encoded_password, headers, login, PASSWORD


def test_account_actions_have_safe_attributed_history(api):
    c, _, _ = api
    admin = headers(login(c, "admin").json()["access_token"])
    actor = c.get("/auth/me", headers=admin).json()["id"]
    response = c.post("/users", headers=admin, json={"username":"activity.example", "full_name":"Example",
                      "role":"AUDITOR", "password":PASSWORD})
    assert response.status_code == 201
    user = response.json()
    path = f"/users/{user['id']}"
    assert c.patch(path, headers=admin, json={"full_name":"Renamed"}).status_code == 200
    assert c.patch(path, headers=admin, json={"full_name":"Renamed"}).status_code == 200
    assert c.patch(path + "/access", headers=admin, json={"role":"ADMIN", "is_active":False}).status_code == 200
    assert c.patch(path + "/access", headers=admin, json={"is_active":True}).status_code == 200
    assert c.post(path + "/reset-password", headers=admin,
                  json={"admin_password":PASSWORD,"new_password":"activity reset passphrase"}).status_code == 204
    employee = headers(login(c, user["username"], "activity reset passphrase").json()["access_token"])
    assert c.post("/auth/change-password", headers=employee,
                  json={"current_password":"activity reset passphrase","new_password":"activity changed passphrase"}).status_code == 204
    response = c.get("/admin-activity", headers=admin, params={"target_user_id":user["id"]})
    assert response.status_code == 200
    events = list(reversed(response.json()["items"]))
    assert [e["action"] for e in events] == ["CREATE","PROFILE_UPDATE","ROLE_CHANGE","DEACTIVATED","ACTIVATED","PASSWORD_RESET","PASSWORD_CHANGE"]
    assert [e["actor_user_id"] for e in events] == [actor]*6 + [user["id"]]
    assert all(e["target_user_id"] == user["id"] and e["created_at"].endswith("Z") for e in events)
    assert events[1]["changes"] == {"full_name":{"before":"Example","after":"Renamed"}}
    assert events[-1]["changes"] is None and events[-2]["changes"] is None
    assert PASSWORD not in response.text and "passphrase" not in response.text and "hash" not in response.text


@pytest.mark.parametrize("operation", ["create", "profile", "access", "reset", "change"])
@pytest.mark.parametrize("failure", ["event", "commit"])
def test_activity_failure_rolls_back_account_and_sessions(api, operation, failure):
    c, engine, _ = api
    admin = headers(login(c, "admin").json()["access_token"])
    employee = headers(login(c).json()["access_token"])
    me = c.get("/auth/me", headers=employee).json()
    with Session(engine) as s:
        u = s.get(User, me["id"])
        before = (u.username, u.full_name, u.role, u.is_active, u.password_hash)
    def fail_event(mapper, connection, row):
        # For combined access changes, let ROLE_CHANGE insert first. Failure of
        # the second event must roll back the first event and both field changes.
        if operation != "access" or row.action == "DEACTIVATED":
            raise SQLAlchemyError("private event storage detail")
    def fail_commit(session):
        raise SQLAlchemyError("private commit detail")
    obj, name, callback = ((AdminActivityEvent, "before_insert", fail_event) if failure == "event" else
                          (Session, "before_commit", fail_commit))
    event.listen(obj, name, callback)
    path = f"/users/{me['id']}"
    try:
        if operation == "create":
            response = c.post("/users", headers=admin, json={"username":"rollback.example", "full_name":"Example", "role":"AUDITOR", "password":PASSWORD})
        elif operation == "profile":
            response = c.patch(path, headers=admin, json={"username":"changed.example", "full_name":"Changed"})
        elif operation == "access":
            response = c.patch(path + "/access", headers=admin, json={"role":"ADMIN", "is_active":False})
        elif operation == "reset":
            response = c.post(path + "/reset-password", headers=admin, json={"admin_password":PASSWORD,"new_password":"replacement example passphrase"})
        else:
            response = c.post("/auth/change-password", headers=employee, json={"current_password":PASSWORD,"new_password":"replacement example passphrase"})
        assert response.status_code == 503
        assert "private" not in response.text and PASSWORD not in response.text
    finally:
        event.remove(obj, name, callback)
    with Session(engine) as s:
        u = s.get(User, me["id"])
        assert (u.username, u.full_name, u.role, u.is_active, u.password_hash) == before
        assert s.scalar(select(func.count()).select_from(User)) == 3
        assert s.scalar(select(func.count()).select_from(AdminActivityEvent)) == 0
    assert c.get("/auth/me", headers=employee).status_code == 200


@pytest.mark.parametrize("identity,status", [(None,401),("auditor",403)])
def test_history_is_admin_only(api, identity, status):
    c, _, _ = api
    auth = {} if identity is None else headers(login(c, identity).json()["access_token"])
    assert c.get("/admin-activity", headers=auth).status_code == status


def test_filters_pagination_and_rejected_operations(api):
    c, engine, _ = api
    admin = headers(login(c, "admin").json()["access_token"])
    actor = c.get("/auth/me", headers=admin).json()["id"]
    users = []
    for name in ["example.one", "example.two"]:
        response = c.post("/users", headers=admin, json={"username":name,"full_name":"Example","role":"AUDITOR","password":PASSWORD})
        assert response.status_code == 201
        users.append(response.json())
    path = f"/users/{users[0]['id']}"
    assert c.patch(path, headers=admin, json={"username":"example.changed"}).status_code == 200
    assert c.patch(path, headers=admin, json={"username":"example.changed"}).status_code == 200
    assert c.patch(path + "/access", headers=admin, json={"role":"AUDITOR"}).status_code == 200
    assert c.patch(path, headers=admin, json={"username":"example.two"}).status_code == 409
    assert c.post(path + "/reset-password", headers=admin, json={"admin_password":"incorrect","new_password":"replacement example passphrase"}).status_code == 401
    assert c.patch(f"/users/{actor}/access", headers=admin, json={"is_active":False}).status_code == 409
    assert c.patch(path, headers=admin, json={"actor_user_id":actor}).status_code == 422
    page = c.get("/admin-activity?page_size=1", headers=admin).json()
    assert page["total"] == 3 and len(page["items"]) == 1
    next_page = c.get("/admin-activity?page_size=1&page=2", headers=admin).json()
    assert page["items"][0]["id"] > next_page["items"][0]["id"]
    assert c.get("/admin-activity", headers=admin, params={"action":"PROFILE_UPDATE","actor_user_id":actor,"target_user_id":users[0]["id"]}).json()["total"] == 1
    for params in [{"page":0},{"page_size":101},{"action":"' OR 1=1 --"},{"actor_user_id":0}]:
        assert c.get("/admin-activity", headers=admin, params=params).status_code == 422
    for method in ["post", "patch", "delete"]:
        assert c.request(method, "/admin-activity", headers=admin, json={}).status_code == 405


@pytest.mark.parametrize("invalid", [{"action":"UNKNOWN"},{"actor_user_id":999999},{"target_user_id":999999}])
def test_activity_database_constraints(api, invalid):
    _, engine, _ = api
    with Session(engine) as s:
        actor = s.scalar(select(User.id).order_by(User.id))
        with constraint_violation():
            with s.begin_nested():
                s.add(AdminActivityEvent(**({"actor_user_id":actor,"target_user_id":actor,"action":"CREATE"} | invalid)))
                s.flush()
