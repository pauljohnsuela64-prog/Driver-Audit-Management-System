"""Revocation must win over an account mutation paused after initial authorization."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
import backend.api.users as routes
from backend.models import AdminActivityEvent, User
from tests.test_auth import api, auth_engine, encoded_password, headers, login, PASSWORD


@pytest.mark.parametrize("operation", ["create", "profile"])
@pytest.mark.parametrize("revocation", ["demote", "disable", "logout"])
def test_account_mutation_rechecks_authority(api, monkeypatch, operation, revocation):
    c, engine, _ = api
    original_admin = headers(login(c, "admin").json()["access_token"])
    first = c.get("/auth/me", headers=original_admin).json()
    created = c.post("/users", headers=original_admin, json={"username":"review.admin",
                     "full_name":"Review Admin", "role":"ADMIN", "password":PASSWORD})
    assert created.status_code == 201
    other_admin = headers(login(c, "review.admin").json()["access_token"])
    target = next(u for u in c.get("/users", headers=other_admin).json()["items"] if u["username"] == "auditor")
    authorized, resume = Event(), Event()
    original_service = routes.create_user if operation == "create" else routes.update_user
    def paused(*args, **kwargs):
        authorized.set()
        assert resume.wait(10)
        return original_service(*args, **kwargs)
    monkeypatch.setattr(routes, "create_user" if operation == "create" else "update_user", paused)
    def stale_request():
        if operation == "create":
            return c.post("/users", headers=original_admin, json={"username":"unauthorized.admin",
                          "full_name":"Rejected Admin", "role":"ADMIN", "password":PASSWORD})
        return c.patch(f"/users/{target['id']}", headers=original_admin, json={"username":"unauthorized.rename"})
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(stale_request)
        assert authorized.wait(10)
        try:
            if revocation == "logout":
                response = c.post("/auth/logout", headers=original_admin)
                assert response.status_code == 204
            else:
                response = c.patch(f"/users/{first['id']}/access", headers=other_admin,
                                   json={"role":"AUDITOR"} if revocation == "demote" else {"is_active":False})
                assert response.status_code == 200
            with Session(engine) as s:
                event_count = s.scalar(select(func.count()).select_from(AdminActivityEvent))
        finally:
            resume.set()
        stale = pending.result(timeout=15)
    assert stale.status_code == 401
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(User)) == 4
        assert s.get(User, target["id"]).username == "auditor"
        assert s.scalar(select(func.count()).select_from(AdminActivityEvent)) == event_count
