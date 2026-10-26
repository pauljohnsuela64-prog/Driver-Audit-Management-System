"""Audit API contract, isolation, and failure tests in both database modes."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models import AuditRecord, AuditEvent, User
from tests.test_auth import api, auth_engine, encoded_password, headers, login

PAYLOAD = {"driver_name": "Example Driver", "audit_date": "2026-10-26",
           "station": "Example Station", "plate_number": "EXAMPLE-1"}


@pytest.fixture
def audits(api):
    client, engine, app = api
    auditor = headers(login(client).json()["access_token"])
    admin = headers(login(client, "admin").json()["access_token"])
    return client, engine, auditor, admin


def create(client, auth, **fields):
    response = client.post("/audits", headers=auth, json=PAYLOAD | fields)
    assert response.status_code == 201, response.text
    return response.json()


def match(auth, version=1):
    return auth | {"If-Match": f'"{version}"'}


def test_crud_history_snapshot_and_duplicate_plate(audits):
    c, engine, auditor, admin = audits
    record = create(c, auditor, helper_name="  ", remarks=" Example ")
    duplicate = create(c, auditor)
    assert duplicate["id"] != record["id"]
    assert record["helper_name"] is None and record["remarks"] == "Example"
    assert record["audited_by_name"] == "auditor"
    assert record["created_at"].endswith("Z")
    path = f"/audits/{record['id']}"
    with Session(engine) as s, s.begin():
        s.get(User, record["audited_by_user_id"]).full_name = "Renamed"
    edited = c.patch(path, headers=match(admin), json={"station": "Changed"})
    assert edited.status_code == 200 and edited.headers["etag"] == '"2"'
    assert edited.json()["audited_by_name"] == "auditor"
    assert c.patch(path, headers=match(auditor), json={"station": "Stale"}).status_code == 412
    assert c.delete(path, headers=match(auditor, 2)).status_code == 403
    assert c.delete(path, headers=match(admin, 2)).status_code == 204
    assert c.get(path, headers=admin).status_code == 404
    assert c.get(path + "?include_deleted=true", headers=auditor).status_code == 403
    assert c.get(path + "?include_deleted=true", headers=admin).json()["version"] == 3
    assert c.patch(path, headers=match(admin, 3), json={"station": "No"}).status_code == 404
    assert c.delete(path, headers=match(admin, 3)).status_code == 404
    assert c.get(path + "/history", headers=admin).status_code == 404
    events = c.get(path + "/history?include_deleted=true", headers=admin).json()["items"]
    assert [e["action"] for e in events] == ["CREATE", "UPDATE", "DELETE"]
    assert events[0]["before_data"] is None
    assert events[1]["before_data"] == events[0]["after_data"]
    assert events[2]["before_data"] == events[1]["after_data"]
    assert events[2]["after_data"]["deleted_at"]
    assert events[1]["actor_user_id"] != events[0]["actor_user_id"]
    assert c.get("/audits", headers=auditor).json()["total"] == 1
    assert c.get("/audits?include_deleted=true", headers=admin).json()["total"] == 2


def test_ownership_uses_id_and_optional_clear(audits, encoded_password):
    c, engine, auditor, admin = audits
    with Session(engine) as s, s.begin():
        s.add(User(username="other", full_name="auditor", password_hash=encoded_password, role="AUDITOR"))
    other = headers(login(c, "other").json()["access_token"])
    r = create(c, auditor, helper_name="Helper", remarks="Remark")
    path = f"/audits/{r['id']}"
    assert c.get(path, headers=other).status_code == 200
    assert c.get(path + "/history", headers=other).status_code == 200
    assert c.patch(path, headers=match(other), json={"remarks": "No"}).status_code == 403
    changed = c.patch(path, headers=match(auditor), json={"helper_name": None, "remarks": None})
    assert changed.status_code == 200
    assert changed.json()["helper_name"] is None and changed.json()["remarks"] is None
    assert changed.json()["driver_name"] == PAYLOAD["driver_name"]


@pytest.mark.parametrize("field,value", [
    ("driver_name", " "), ("driver_name", None), ("driver_name", 12), ("driver_name", "a"*201),
    ("station", "a"*151), ("plate_number", "a"*31), ("helper_name", "a"*201),
    ("remarks", "a"*10001), ("audit_date", 0), ("audit_date", "2026-02-30"),
    ("audit_date", "2026-10-26T00:00:00Z"), ("audit_date", "0001-01-01"), ("audited_by_name", "Forged"),
    ("audited_by_user_id", 1), ("version", 9), ("deleted_at", None), ("idempotency_key", "x"),
])
def test_invalid_create_and_patch(audits, field, value):
    c, _, auditor, _ = audits
    assert c.post("/audits", headers=auditor, json=PAYLOAD | {field:value}).status_code == 422
    r = create(c, auditor)
    assert c.patch(f"/audits/{r['id']}", headers=match(auditor), json={field:value}).status_code == 422


def test_authentication_required_for_every_route(api):
    c, _, _ = api
    for method, path, body in [("post", "/audits", PAYLOAD), ("get", "/audits", None),
            ("get", "/audits/1", None), ("patch", "/audits/1", {"remarks":"x"}),
            ("delete", "/audits/1", None), ("get", "/audits/1/history", None)]:
        assert c.request(method, path, json=body).status_code == 401


@pytest.mark.parametrize("version,status", [(None,428), ("1",422), ('W/"1"',422), ('"0"',422), ('"9"',412)])
def test_preconditions(audits, version, status):
    c, _, auditor, admin = audits
    r = create(c, auditor)
    for method, h in [("patch",auditor), ("delete",admin)]:
        if version is not None:
            h = h | {"If-Match":version}
        response = c.request(method, f"/audits/{r['id']}", headers=h,
                             json={"remarks":"x"} if method == "patch" else None)
        assert response.status_code == status


def test_filter_sort_page_and_literal_search(audits):
    c, _, auditor, admin = audits
    a = create(c, auditor, driver_name="Percent% Driver", audit_date="2026-01-01")
    b = create(c, admin, driver_name="Second Driver", audit_date="2026-02-01", station="Second")
    page = c.get("/audits", headers=auditor, params={"sort":"audit_date", "page_size":1}).json()
    assert page["total"] == 2 and page["items"][0]["id"] == a["id"]
    assert c.get("/audits?page_size=1&page=2&sort=audit_date", headers=auditor).json()["items"][0]["id"] == b["id"]
    for params, expected in [({"driver_name":"%"},1), ({"driver_name":"' OR 1=1 --"},0),
        ({"station":"Second"},1), ({"plate_number":"EXAMPLE"},2),
        ({"date_from":"2026-02-01", "date_to":"2026-02-01"},1),
        ({"audited_by_user_id":a["audited_by_user_id"]},1)]:
        assert c.get("/audits", headers=auditor, params=params).json()["total"] == expected
    for params in [{"page":0},{"page_size":101},{"sort":"password_hash"},
                   {"date_from":"2026-02-01","date_to":"2026-01-01"},{"date_from":"0"}]:
        assert c.get("/audits", headers=auditor, params=params).status_code == 422
    assert c.get("/audits?include_deleted=true", headers=auditor).status_code == 403


def test_idempotency_original_payload_creator_and_deletion(audits):
    c, _, auditor, admin = audits
    key = str(uuid4())
    h = auditor | {"Idempotency-Key":key}
    r = create(c, h)
    path = f"/audits/{r['id']}"
    assert c.patch(path, headers=match(auditor), json={"remarks":"edited"}).status_code == 200
    replay = c.post("/audits", headers=h, json=PAYLOAD | {"driver_name":"  Example Driver  ", "helper_name":" "})
    assert replay.status_code == 200 and replay.json()["version"] == 2
    assert c.post("/audits", headers=h, json=PAYLOAD | {"remarks":"edited"}).status_code == 409
    assert c.post("/audits", headers=admin | {"Idempotency-Key":key}, json=PAYLOAD).status_code == 409
    assert c.post("/audits", headers=auditor | {"Idempotency-Key":"bad"}, json=PAYLOAD).status_code == 422
    assert c.get(path + "/history", headers=auditor).json()["total"] == 2
    assert c.delete(path, headers=match(admin,2)).status_code == 204
    assert c.post("/audits", headers=h, json=PAYLOAD).status_code == 409


@pytest.mark.parametrize("operation", ["create","patch","delete"])
def test_history_failure_rolls_back(audits, operation):
    c, engine, auditor, admin = audits
    r = None if operation == "create" else create(c,auditor)
    def fail(mapper, connection, target):
        raise SQLAlchemyError("private database detail")
    event.listen(AuditEvent, "before_insert", fail)
    try:
        if operation == "create":
            response = c.post("/audits", headers=auditor, json=PAYLOAD)
        else:
            response = c.request(operation if operation == "delete" else "patch", f"/audits/{r['id']}",
                                 headers=match(admin), json={"remarks":"change"} if operation == "patch" else None)
        assert response.status_code == 503
        assert "private" not in response.text
    finally:
        event.remove(AuditEvent, "before_insert", fail)
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(AuditEvent)) == (0 if r is None else 1)
        if r:
            stored = s.get(AuditRecord,r["id"])
            assert stored.version == 1 and stored.deleted_at is None and stored.remarks is None
        else:
            assert s.scalar(select(func.count()).select_from(AuditRecord)) == 0


def test_outer_rollback_after_successful_create(audits):
    c, engine, auditor, _ = audits
    def fail(session):
        if not session.in_nested_transaction():
            raise SQLAlchemyError("commit failure")
    event.listen(Session, "before_commit", fail)
    try:
        assert c.post("/audits", headers=auditor, json=PAYLOAD).status_code == 503
    finally:
        event.remove(Session, "before_commit", fail)
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(AuditRecord)) == 0


@pytest.mark.parametrize("operation", ["retry", "update", "delete_vs_update"])
def test_mysql_concurrent_requests(audits, operation):
    c, engine, auditor, admin = audits
    if engine.dialect.name != "mysql":
        # SQLite is not the production concurrency contract; exercise sequential equivalents.
        workers = 1
    else:
        workers = 2
    r = create(c,auditor) if operation != "retry" else None
    barrier = Barrier(workers)
    key = str(uuid4())
    def call(i):
        barrier.wait(timeout=10)
        if operation == "retry":
            return c.post("/audits", headers=auditor | {"Idempotency-Key":key}, json=PAYLOAD)
        if operation == "delete_vs_update" and i == 0:
            return c.delete(f"/audits/{r['id']}",headers=match(admin))
        return c.patch(f"/audits/{r['id']}",headers=match(auditor), json={"remarks":str(i)})
    sql_barrier = Barrier(workers)
    def overlap(connection, cursor, statement, parameters, context, executemany):
        if operation == "retry" and statement.startswith("INSERT INTO audit_records"):
            sql_barrier.wait(timeout=10)
        elif operation != "retry" and "FROM audit_records" in statement and "FOR UPDATE" in statement:
            sql_barrier.wait(timeout=10)
    event.listen(engine, "before_cursor_execute", overlap)
    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            responses = list(executor.map(call,range(workers)))
    finally:
        event.remove(engine, "before_cursor_execute", overlap)
    if workers == 1:
        responses.append(call(1))
    statuses = sorted(x.status_code for x in responses)
    if operation == "retry":
        assert statuses == [200,201]
        assert responses[0].json()["id"] == responses[1].json()["id"]
    elif operation == "update":
        assert statuses == [200,412]
    else:
        assert statuses in ([204,404],[200,412])
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(AuditRecord)) == 1
        assert s.scalar(select(func.count()).select_from(AuditEvent)) == (1 if operation == "retry" else 2)


@pytest.mark.parametrize("change", ["disabled", "role", "logout"])
def test_current_identity_enforced_on_audits(audits, change):
    c, engine, auditor, admin = audits
    r = create(c,admin)
    if change == "logout":
        assert c.post("/auth/logout",headers=admin).status_code == 204
    else:
        with Session(engine) as s, s.begin():
            user = s.get(User,r["audited_by_user_id"])
            if change == "disabled":
                user.is_active = False
            else:
                user.role = "AUDITOR"
    response = c.delete(f"/audits/{r['id']}",headers=match(admin))
    assert response.status_code == (403 if change == "role" else 401)


def test_empty_patch_missing_record_and_noop(audits):
    c, _, auditor, _ = audits
    r = create(c,auditor)
    path = f"/audits/{r['id']}"
    assert c.patch(path,headers=match(auditor),json={}).status_code == 422
    for route in ["/audits/999999", "/audits/999999/history"]:
        assert c.get(route,headers=auditor).status_code == 404
    response = c.patch(path,headers=match(auditor),json={"station":PAYLOAD["station"]})
    assert response.status_code == 200 and response.json()["version"] == 2
    page = c.get(path + "/history?page_size=1&page=2",headers=auditor).json()
    assert page["total"] == 2 and page["items"][0]["action"] == "UPDATE"
    assert not {"password_hash", "token_hash", "idempotency_key"} & set(response.json())


@pytest.mark.parametrize("field", ["driver_name", "audit_date", "station", "plate_number"])
def test_missing_required_fields(audits, field):
    c, _, auditor, _ = audits
    payload = dict(PAYLOAD)
    del payload[field]
    assert c.post("/audits",headers=auditor,json=payload).status_code == 422


@pytest.mark.parametrize("operation", ["patch", "delete"])
def test_outer_commit_failure_on_existing_record(audits, operation):
    c, engine, auditor, admin = audits
    r = create(c,auditor)
    def fail(session):
        raise SQLAlchemyError("private commit detail")
    event.listen(Session, "before_commit", fail)
    try:
        response = c.request(operation,f"/audits/{r['id']}",headers=match(admin),
                             json={"remarks":"change"} if operation == "patch" else None)
        assert response.status_code == 503 and "private" not in response.text
    finally:
        event.remove(Session,"before_commit",fail)
    with Session(engine) as s:
        record = s.get(AuditRecord,r["id"])
        assert record.version == 1 and record.deleted_at is None and record.remarks is None
        assert s.scalar(select(func.count()).select_from(AuditEvent)) == 1
