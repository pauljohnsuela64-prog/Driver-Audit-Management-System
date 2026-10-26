import pytest
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
