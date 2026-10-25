"""Safety checks shared by opt-in live MySQL tests."""
import os

from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from backend.core.database import make_engine


def mysql_test_engine():
    value = os.getenv("DAMS_TEST_DATABASE_URL")
    if not value:
        raise ValueError("DAMS_TEST_DATABASE_URL is required for live MySQL verification")
    url = make_url(value)
    if (url.drivername != "mysql+pymysql" or not url.database
            or not url.database.startswith("driver_audit_test_")
            or not url.username or url.username.lower() == "root" or not url.password
            or set(url.query) - {"charset"}
            or url.query.get("charset", "utf8mb4") != "utf8mb4"):
        raise ValueError("Live tests require a dedicated non-root account and driver_audit_test_ database")
    engine = make_engine(url)
    try:
        with engine.connect() as connection:
            if inspect(connection).get_table_names():
                raise ValueError("Test database must be empty; refusing to modify existing tables")
        return engine
    except BaseException:
        engine.dispose()
        raise
