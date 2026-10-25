"""Live runtime-account bootstrap concurrency gate."""
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.core.database import make_engine
from backend.core.errors import ServiceError
from backend.models import User
from backend.schemas.auth import BootstrapRequest
from backend.services.bootstrap import bootstrap_admin
from tests.test_mysql_runtime import live_database

pytestmark = pytest.mark.mysql


def test_runtime_bootstrap_serializes_concurrent_creators(live_database):
    value = os.getenv("DAMS_TEST_RUNTIME_URL")
    if not value:
        pytest.skip("Dedicated runtime credentials required")
    url = make_url(value)
    target = live_database.url
    assert url.username == "dams_test_app" and url.password
    assert not set(url.query) - {"charset"}
    assert url.query.get("charset", "utf8mb4") == "utf8mb4"
    assert (url.drivername, url.host, url.port, url.database) == (target.drivername, target.host, target.port, target.database)
    runtime = make_engine(url)
    try:
        with runtime.connect() as c:
            assert c.scalar(text("SELECT CURRENT_USER()")) == "dams_test_app@localhost"
        def create(name):
            data = BootstrapRequest(username=name, full_name="Test", password="concurrency test passphrase!")
            try:
                bootstrap_admin(runtime, data)
                return "created"
            except ServiceError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(create, ["first", "second"]))
        assert sorted(outcomes) == ["created", "setup_refused"]
        with Session(runtime) as s:
            assert s.scalar(select(func.count()).select_from(User)) == 1
    finally:
        runtime.dispose()
