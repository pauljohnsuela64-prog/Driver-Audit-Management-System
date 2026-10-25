"""Authentication API tests; --mysql uses dams_test_app for application traffic."""
import os
from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.api.dependencies import get_auth_service, require_roles
from backend.core.config import runtime_database_url
from backend.core.database import make_engine, utcnow
from backend.core.errors import ServiceError
from backend.core.security import hash_password, token_hash, verify_password
from backend.main import create_app
from backend.models import AuthSession, Base, User
from backend.schemas.auth import BootstrapRequest
from backend.services.bootstrap import bootstrap_admin
from tests.mysql_support import mysql_test_engine

PASSWORD = "test-only long passphrase!"


@pytest.fixture(scope="module")
def encoded_password():
    return hash_password(PASSWORD)


@pytest.fixture
def auth_engine(request, tmp_path):
    migrator = None
    if request.config.getoption("--mysql"):
        value = os.getenv("DAMS_TEST_RUNTIME_URL")
        if not value:
            pytest.fail("--mysql API tests require DAMS_TEST_RUNTIME_URL")
        runtime = make_url(value)
        target = make_url(os.environ["DAMS_TEST_DATABASE_URL"])
        if (runtime.username != "dams_test_app" or not runtime.password
                or set(runtime.query) - {"charset"}
                or runtime.query.get("charset", "utf8mb4") != "utf8mb4"
                or (runtime.drivername, runtime.host, runtime.port, runtime.database)
                != (target.drivername, target.host, target.port, target.database)):
            pytest.fail("Runtime credentials must target the isolated test database")
        migrator = mysql_test_engine()
        cfg = Config("alembic.ini")
        with migrator.connect() as c:
            cfg.attributes["connection"] = c
            command.upgrade(cfg, "head")
        engine = make_engine(runtime)
    else:
        engine = make_engine(f"sqlite:///{(tmp_path / 'auth.db').as_posix()}")
        Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        if migrator:
            try:
                with migrator.connect() as c:
                    cfg.attributes["connection"] = c
                    command.downgrade(cfg, "base")
                    c.execute(text("DROP TABLE alembic_version"))
                    c.commit()
            finally:
                migrator.dispose()


@pytest.fixture
def api(auth_engine, encoded_password):
    with Session(auth_engine) as s, s.begin():
        s.add_all([User(username=name, full_name=name, password_hash=encoded_password,
                        role=role, is_active=active) for name, role, active in
                   [("admin", "ADMIN", True), ("auditor", "AUDITOR", True), ("disabled", "AUDITOR", False)]])
    app = create_app(engine=auth_engine)

    @app.get("/test/admin")
    def admin_only(user=Depends(require_roles("ADMIN"))):
        return {"role": user.role}

    @app.get("/test/audit")
    def audit_access(user=Depends(require_roles("ADMIN", "AUDITOR"))):
        return {"role": user.role}

    with TestClient(app) as client:
        yield client, auth_engine, app


def login(client, username="auditor", password=PASSWORD):
    return client.post("/auth/login", json={"username": username, "password": password})


def headers(token):
    return {"Authorization": "Bearer " + token}


def test_login_me_logout_hash_storage(api, caplog):
    client, engine, _ = api
    response = login(client)
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert len(token) == 43 and response.json()["token_type"] == "bearer"
    assert response.headers["cache-control"] == "no-store"
    with Session(engine) as s:
        record = s.scalar(select(AuthSession))
        assert record.token_hash == token_hash(token) and record.token_hash != token
        assert record.expires_at - record.created_at == timedelta(hours=8)
    me = client.get("/auth/me", headers=headers(token))
    assert me.status_code == 200 and me.json()["role"] == "AUDITOR"
    assert set(me.json()) == {"id", "username", "full_name", "role"}
    assert client.post("/auth/logout", headers=headers(token)).status_code == 204
    assert client.get("/auth/me", headers=headers(token)).status_code == 401
    assert client.post("/auth/logout", headers=headers(token)).status_code == 401
    assert PASSWORD not in caplog.text and token not in caplog.text


@pytest.mark.parametrize("username,password", [("auditor", "wrong"), ("unknown", PASSWORD), ("disabled", PASSWORD), ("' OR 1=1 --", PASSWORD)])
def test_invalid_credentials_are_indistinguishable(api, username, password):
    client, engine, _ = api
    response = login(client, username, password)
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "unauthorized", "message": "Invalid credentials or session"}}
    assert response.headers["www-authenticate"] == "Bearer"
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(AuthSession)) == 0


@pytest.mark.parametrize("authorization", [None, "", "Basic xyz", "Bearer short", "Bearer " + "a" * 44, "Bearer " + "a" * 43, "Bearer " + "!" * 43])
def test_missing_and_malformed_tokens(api, authorization):
    client, _, _ = api
    h = {} if authorization is None else {"Authorization": authorization}
    for path in ("/auth/me", "/test/admin", "/test/audit"):
        assert client.get(path, headers=h).status_code == 401


@pytest.mark.parametrize("change", ["disabled", "expired", "revoked"])
def test_existing_session_rejected_after_account_or_session_change(api, change):
    client, engine, _ = api
    token = login(client).json()["access_token"]
    with Session(engine) as s, s.begin():
        record = s.scalar(select(AuthSession))
        if change == "disabled":
            s.get(User, record.user_id).is_active = False
        elif change == "revoked":
            record.revoked_at = utcnow()
        else:
            record.created_at = utcnow() - timedelta(hours=9)
            record.expires_at = utcnow() - timedelta(hours=1)
    assert client.get("/auth/me", headers=headers(token)).status_code == 401


@pytest.mark.parametrize("role,admin_status", [("admin", 200), ("auditor", 403)])
def test_role_enforcement(api, role, admin_status):
    client, _, _ = api
    token = login(client, role).json()["access_token"]
    assert client.get("/test/admin", headers=headers(token)).status_code == admin_status
    assert client.get("/test/audit", headers=headers(token)).status_code == 200


def test_role_changes_take_effect_for_existing_sessions(api):
    client, engine, _ = api
    token = login(client, "admin").json()["access_token"]
    with Session(engine) as s, s.begin():
        s.scalar(select(User).where(User.username == "admin")).role = "AUDITOR"
    assert client.get("/test/admin", headers=headers(token)).status_code == 403


@pytest.mark.parametrize("payload", [{"username": "auditor", "password": "x" * 129}, {"username": "auditor", "password": PASSWORD, "role": "ADMIN"}, {"username": "auditor", "password": {"secret": PASSWORD}}])
def test_validation_does_not_echo_secrets(api, payload):
    response = api[0].post("/auth/login", json=payload)
    assert response.status_code == 422 and PASSWORD not in response.text
    assert response.json()["error"]["code"] == "invalid_request"


def test_failure_rolls_back_before_response(api):
    client, engine, _ = api
    def fail_commit(session):
        raise SQLAlchemyError("secret diagnostic must not escape")
    event.listen(Session, "before_commit", fail_commit)
    try:
        response = login(client)
        assert response.status_code == 503
        assert "secret diagnostic" not in response.text
    finally:
        event.remove(Session, "before_commit", fail_commit)
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_service_failure_is_sanitized(api, caplog):
    client, _, app = api
    def failure():
        raise RuntimeError("sensitive service diagnostic")
    app.dependency_overrides[get_auth_service] = failure
    response = login(client)
    assert response.status_code == 500
    assert "sensitive" not in response.text and "sensitive" not in caplog.text


def test_login_throttling(api):
    client, _, _ = api
    for _ in range(10):
        assert login(client, "unknown", "wrong").status_code == 401
    response = login(client)
    assert response.status_code == 429 and response.headers["retry-after"] == "60"


def test_health_openapi_and_scope(api):
    client, engine, _ = api
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/missing").json()["error"]["code"] == "http_error"
    spec = create_app(engine=engine).openapi()
    assert set(spec["paths"]) == {"/health", "/auth/login", "/auth/logout", "/auth/me"}
    assert spec["paths"]["/auth/me"]["get"]["security"]


def test_password_hashes():
    one, two = hash_password(PASSWORD), hash_password(PASSWORD)
    assert one.startswith("$argon2id$") and one != two
    assert verify_password(one, PASSWORD)
    assert not verify_password(one, "wrong")
    assert not verify_password("invalid hash", PASSWORD)
    with pytest.raises(ValueError):
        hash_password("short")


def bootstrap_request():
    return BootstrapRequest(username="first-admin", full_name="Test Administrator", password=PASSWORD)


def test_bootstrap_and_explicit_recovery(auth_engine):
    bootstrap_admin(auth_engine, bootstrap_request())
    with pytest.raises(ServiceError, match="setup_refused"):
        bootstrap_admin(auth_engine, bootstrap_request())
    with Session(auth_engine) as s, s.begin():
        admin = s.scalar(select(User))
        assert admin.role == "ADMIN" and verify_password(admin.password_hash, PASSWORD)
        s.add(AuthSession(user_id=admin.id, token_hash="a" * 64, expires_at=utcnow()+timedelta(hours=1)))
        admin.is_active = False
    bootstrap_admin(auth_engine, bootstrap_request(), recover=True)
    with Session(auth_engine) as s:
        assert s.scalar(select(User)).is_active
        assert s.scalar(select(AuthSession)).revoked_at is not None


def test_bootstrap_refuses_existing_users_and_nonadmin_recovery(api):
    with pytest.raises(ServiceError):
        bootstrap_admin(api[1], bootstrap_request())
    request = BootstrapRequest(username="auditor", full_name="Test", password=PASSWORD)
    with pytest.raises(ServiceError, match="recovery_refused"):
        bootstrap_admin(api[1], request, recover=True)


@pytest.mark.parametrize("value", ["", "mysql+pymysql://dams_prod_migrate:dummy@localhost/driver_audit_db", "mysql+pymysql://root:dummy@localhost/driver_audit_db", "mysql+pymysql://dams_prod_app:dummy@localhost/driver_audit_test_phase1", "malformed"])
def test_runtime_configuration_rejects_nonruntime(monkeypatch, value):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("DAMS_PROD_RUNTIME_URL", value)
    with pytest.raises(ValueError):
        runtime_database_url()


def test_invalid_authorization_role_rejected():
    with pytest.raises(ValueError):
        require_roles("SUPERADMIN")


def test_login_upgrades_legacy_hash(api):
    from argon2 import PasswordHasher
    from backend.core.security import HASHER
    client, engine, _ = api
    legacy = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(PASSWORD)
    with Session(engine) as s, s.begin():
        s.scalar(select(User).where(User.username == "auditor")).password_hash = legacy
    assert login(client).status_code == 200
    with Session(engine) as s:
        stored = s.scalar(select(User).where(User.username == "auditor")).password_hash
        assert stored != legacy and not HASHER.check_needs_rehash(stored)
        assert verify_password(stored, PASSWORD)


def test_concurrent_logins_and_session_specific_logout(api):
    from concurrent.futures import ThreadPoolExecutor
    client, engine, _ = api
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: login(client), range(2)))
    assert all(r.status_code == 200 for r in responses)
    first, second = [r.json()["access_token"] for r in responses]
    assert first != second
    assert client.post("/auth/logout", headers=headers(first)).status_code == 204
    assert client.get("/auth/me", headers=headers(first)).status_code == 401
    assert client.get("/auth/me", headers=headers(second)).status_code == 200


def test_bootstrap_transaction_failure_leaves_no_admin(auth_engine):
    def fail(session):
        raise SQLAlchemyError("simulated commit failure")
    event.listen(Session, "before_commit", fail)
    try:
        with pytest.raises(SQLAlchemyError):
            bootstrap_admin(auth_engine, bootstrap_request())
    finally:
        event.remove(Session, "before_commit", fail)
    with Session(auth_engine) as s:
        assert s.scalar(select(func.count()).select_from(User)) == 0


def test_recovery_changes_password_and_invalidates_session(auth_engine):
    bootstrap_admin(auth_engine, bootstrap_request())
    with TestClient(create_app(engine=auth_engine)) as client:
        token = login(client, "first-admin").json()["access_token"]
        updated = BootstrapRequest(username="first-admin", full_name="Ignored", password="replacement test passphrase!")
        bootstrap_admin(auth_engine, updated, recover=True)
        assert client.get("/auth/me", headers=headers(token)).status_code == 401
        assert login(client, "first-admin").status_code == 401
        assert login(client, "first-admin", "replacement test passphrase!").status_code == 200


def test_database_query_error_is_sanitized(api, monkeypatch, caplog):
    from backend.repositories.auth import AuthRepository
    def fail(self, username):
        raise SQLAlchemyError("private connection diagnostic")
    monkeypatch.setattr(AuthRepository, "find_user", fail)
    response = login(api[0])
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert "private connection" not in response.text + caplog.text


def test_bootstrap_cli_uses_hidden_password_input_and_no_password_arguments(monkeypatch, auth_engine, capsys):
    from scripts import bootstrap_admin as cli
    monkeypatch.setattr("sys.argv", ["bootstrap_admin"])
    answers = iter(["local-admin", "Local test admin"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(cli, "getpass", lambda _: PASSWORD)
    monkeypatch.setattr(cli, "runtime_database_url", lambda: "not-used")
    monkeypatch.setattr(cli, "make_engine", lambda _: auth_engine)
    cli.main()
    output = capsys.readouterr()
    assert PASSWORD not in output.out + output.err
    with Session(auth_engine) as s:
        assert s.scalar(select(User)).username == "local-admin"


@pytest.mark.parametrize("query", ["user=dams_prod_migrate", "database=other", "password=override", "charset=latin1", "charset=utf8mb4&charset=latin1"])
def test_runtime_configuration_rejects_driver_overrides(monkeypatch, query):
    monkeypatch.setenv("DAMS_PROD_RUNTIME_URL", "mysql+pymysql://dams_prod_app:dummy@localhost/driver_audit_db?" + query)
    with pytest.raises(ValueError):
        runtime_database_url()


def test_logout_commit_failure_keeps_token_valid(api):
    client, engine, _ = api
    token = login(client).json()["access_token"]
    def fail(session):
        raise SQLAlchemyError("simulated failure")
    event.listen(Session, "before_commit", fail)
    try:
        assert client.post("/auth/logout", headers=headers(token)).status_code == 503
    finally:
        event.remove(Session, "before_commit", fail)
    assert client.get("/auth/me", headers=headers(token)).status_code == 200


def test_bootstrap_refuses_echoed_password_fallback(monkeypatch):
    import warnings
    from getpass import GetPassWarning
    from scripts import bootstrap_admin as cli
    def insecure_prompt(prompt):
        warnings.warn("Cannot hide password", GetPassWarning)
        pytest.fail("Must not continue to echoed input")
    monkeypatch.setattr(cli, "getpass", insecure_prompt)
    with pytest.raises(GetPassWarning):
        cli.prompt_password("Password: ")
