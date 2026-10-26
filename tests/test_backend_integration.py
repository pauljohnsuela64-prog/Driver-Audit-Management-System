"""Client-visible account/audit workflow, using only API calls after fixture setup."""
from uuid import uuid4

from tests.test_auth import api, auth_engine, encoded_password, headers, login, PASSWORD


def test_employee_audit_and_password_lifecycle(api):
    c, _, _ = api
    def sign_in(username, password=PASSWORD):
        response = login(c, username, password)
        assert response.status_code == 200
        return headers(response.json()["access_token"])

    admin = sign_in("admin")
    admin_id = c.get("/auth/me", headers=admin).json()["id"]
    employees = []
    for username in ["integration.auditor", "integration.peer"]:
        response = c.post("/users", headers=admin, json={"username": username,
                          "full_name": "Example Auditor", "role": "AUDITOR", "password": PASSWORD})
        assert response.status_code == 201
        employees.append(response.json())
    employee, peer = employees
    owner = sign_in(employee["username"])
    other = sign_in(peer["username"])
    body = {"driver_name": "Example Driver", "audit_date": "2026-10-26",
            "station": "Example Station", "plate_number": "EXAMPLE-1"}
    creation_headers = owner | {"Idempotency-Key": str(uuid4())}
    created = c.post("/audits", headers=creation_headers, json=body)
    assert created.status_code == 201
    record = created.json()
    path = f"/audits/{record['id']}"
    assert record["audited_by_user_id"] == employee["id"]
    assert record["audited_by_name"] == "Example Auditor"
    replay = c.post("/audits", headers=creation_headers, json=body)
    assert replay.status_code == 200 and replay.json()["id"] == record["id"]
    read = c.get(path, headers=owner)
    assert read.status_code == 200 and read.headers["etag"] == '"1"'
    edited = c.patch(path, headers=owner | {"If-Match": read.headers["etag"]},
                     json={"remarks": "Employee edit"})
    assert edited.status_code == 200 and edited.headers["etag"] == '"2"'
    assert c.patch(path, headers=other | {"If-Match": edited.headers["etag"]},
                   json={"remarks": "Forbidden peer edit"}).status_code == 403
    # Even matching employee names cannot confer ownership; later renaming must
    # also preserve the attribution captured when this record was created.
    account_path = f"/users/{employee['id']}"
    assert c.patch(account_path, headers=admin, json={"full_name": "Renamed Employee"}).status_code == 200
    read = c.get(path, headers=admin)
    assert read.status_code == 200 and read.json()["audited_by_name"] == "Example Auditor"
    edited = c.patch(path, headers=admin | {"If-Match": read.headers["etag"]},
                     json={"remarks": "Administrator edit"})
    assert edited.status_code == 200
    assert c.delete(path, headers=admin | {"If-Match": edited.headers["etag"]}).status_code == 204
    assert c.get(path, headers=owner).status_code == 404
    history_path = path + "/history?include_deleted=true"
    response = c.get(history_path, headers=admin)
    assert response.status_code == 200
    history = response.json()
    events = history["items"]
    assert [e["action"] for e in events] == ["CREATE", "UPDATE", "UPDATE", "DELETE"]
    assert [e["actor_user_id"] for e in events] == [employee["id"], employee["id"], admin_id, admin_id]
    for previous, current in zip(events, events[1:]):
        assert previous["after_data"] == current["before_data"]
    assert all(e["after_data"]["audited_by_name"] == "Example Auditor" for e in events)
    assert c.patch(account_path + "/access", headers=admin, json={"is_active": False}).status_code == 200
    assert c.get("/auth/me", headers=owner).status_code == 401
    assert login(c, employee["username"]).status_code == 401
    deleted = c.get(path + "?include_deleted=true", headers=admin)
    assert deleted.status_code == 200 and deleted.json()["audited_by_user_id"] == employee["id"]
    assert deleted.json()["deleted_at"] is not None
    assert c.patch(account_path + "/access", headers=admin, json={"is_active": True}).status_code == 200
    owner = sign_in(employee["username"])
    reset_password = "integration reset passphrase!"
    changed_password = "integration changed passphrase!"
    assert c.post(account_path + "/reset-password", headers=admin,
                  json={"admin_password": PASSWORD, "new_password": reset_password}).status_code == 204
    assert c.get("/auth/me", headers=owner).status_code == 401
    assert login(c, employee["username"]).status_code == 401
    owner = sign_in(employee["username"], reset_password)
    assert c.post("/auth/change-password", headers=owner,
                  json={"current_password": reset_password, "new_password": changed_password}).status_code == 204
    assert c.get("/auth/me", headers=owner).status_code == 401
    assert login(c, employee["username"], reset_password).status_code == 401
    owner = sign_in(employee["username"], changed_password)
    me = c.get("/auth/me", headers=owner).json()
    assert me["id"] == employee["id"] and me["role"] == "AUDITOR"
    assert c.get(history_path, headers=admin).json() == history
