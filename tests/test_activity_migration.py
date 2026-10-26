import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from backend.core.database import make_engine
from tests.mysql_support import mysql_test_engine


def test_activity_revision_preserves_existing_data(request, tmp_path):
    engine = mysql_test_engine() if request.config.getoption("--mysql") else make_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    cfg = Config("alembic.ini")
    try:
        with engine.connect() as c:
            cfg.attributes["connection"] = c
            command.upgrade(cfg, "0001")
            c.execute(text("INSERT INTO users (username, full_name, password_hash, role) VALUES ('migration.example', 'Example', 'test-only', 'ADMIN')"))
            c.commit()
            command.upgrade(cfg, "head")
            c.commit()
            assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
            assert 'admin_activity_events' in inspect(c).get_table_names()
            assert c.scalar(text("SELECT COUNT(*) FROM users")) == 1
            command.downgrade(cfg, "0001")
            c.commit()
            assert 'admin_activity_events' not in inspect(c).get_table_names()
            assert c.scalar(text("SELECT full_name FROM users")) == "Example"
    finally:
        with engine.connect() as c:
            cfg.attributes["connection"] = c
            command.downgrade(cfg, "base")
            c.execute(text("DROP TABLE alembic_version"))
            c.commit()
        engine.dispose()
