import os
from io import StringIO

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from backend.core.database import make_engine
from backend.models import Base
from tests.constraint_support import constraint_violation
from tests.test_foundation import audit, user
from tests.mysql_support import mysql_test_engine


def verify_migrations(engine):
    config = Config("alembic.ini")
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert context.get_current_revision() == ScriptDirectory.from_config(config).get_current_head() == "0001"
        assert compare_metadata(context, Base.metadata) == []
        assert set(inspect(connection).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
        connection.commit()
        with Session(bind=connection) as s:
            u = user()
            s.add(u)
            s.flush()
            s.add_all([audit(u.id), audit(u.id)])
            s.commit()
            # Exercise database constraints on the migrated schema too.
            with constraint_violation():
                with s.begin_nested():
                    s.add(audit(999999))
                    s.flush()
            with constraint_violation():
                with s.begin_nested():
                    s.add(user(role="INVALID", username="bad-role"))
                    s.flush()
            s.rollback()
        command.downgrade(config, "base")
        assert inspect(connection).get_table_names() == ["alembic_version"]
        connection.commit()
        command.upgrade(config, "head")
        command.check(config)
        command.downgrade(config, "base")
        connection.commit()
        # Only the version table created in this verified-empty test database.
        connection.execute(text("DROP TABLE alembic_version"))
        connection.commit()
        assert inspect(connection).get_table_names() == []


def test_sqlite_migration_roundtrip():
    engine = make_engine("sqlite://")
    try:
        verify_migrations(engine)
        verify_migrations(engine)
    finally:
        engine.dispose()


def test_mysql_offline_sql(monkeypatch):
    # Compile the actual revision for MySQL without opening a connection.
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://dams:compile-only@localhost/driver_audit_db")
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    for table in Base.metadata.tables:
        assert f"CREATE TABLE {table}" in sql
    assert "DATETIME(6)" in sql
    assert "DEFAULT CURRENT_TIMESTAMP(6)" in sql
    assert "ENGINE=InnoDB" in sql and "utf8mb4" in sql
    assert "FOREIGN KEY" in sql and "ON DELETE RESTRICT" in sql
    assert "CHECK (version >= 1)" in sql
    assert "UNIQUE (plate_number)" not in sql
    assert "'0001'" in sql


@pytest.mark.mysql
def test_mysql_migration_roundtrip():
    value = os.getenv("DAMS_TEST_DATABASE_URL")
    if not value:
        pytest.skip("DAMS_TEST_DATABASE_URL absent; dedicated empty MySQL test database and credentials required")
    engine = mysql_test_engine()
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT @@session.time_zone")) == "+00:00"
        verify_migrations(engine)
    finally:
        engine.dispose()


def test_mysql_offline_downgrade_keeps_fk_indexes_until_table_drop(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://dams:compile-only@localhost/driver_audit_db")
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)
    command.downgrade(config, "0001:base", sql=True)
    sql = output.getvalue()
    assert "DROP INDEX" not in sql
    positions = [sql.index(f"DROP TABLE {table}") for table in
                 ("audit_events", "auth_sessions", "audit_records", "users")]
    assert positions == sorted(positions)
