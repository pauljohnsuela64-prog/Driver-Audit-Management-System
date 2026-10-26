import pytest
from alembic import command
from alembic import op
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


def test_interrupted_activity_upgrade_preserves_data_and_allows_reviewed_retry(request, tmp_path, monkeypatch):
    engine = mysql_test_engine() if request.config.getoption("--mysql") else make_engine(f"sqlite:///{tmp_path / 'interrupted.db'}")
    cfg = Config("alembic.ini")
    original_index = op.create_index
    def interrupted(name, table, columns, *args, **kwargs):
        if table == "admin_activity_events" and columns == ["target_user_id"]:
            raise RuntimeError("injected activity index failure")
        return original_index(name, table, columns, *args, **kwargs)
    try:
        with engine.connect() as c:
            cfg.attributes["connection"] = c
            command.upgrade(cfg, "0001")
            c.execute(text("INSERT INTO users (username, full_name, password_hash, role) VALUES ('preserved.example', 'Preserved', 'test-only', 'ADMIN')"))
            c.commit()
            monkeypatch.setattr(op, "create_index", interrupted)
            with pytest.raises(RuntimeError, match="injected activity index failure"):
                command.upgrade(cfg, "0002")
            c.rollback()
            assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
            assert c.scalar(text("SELECT full_name FROM users")) == "Preserved"
            assert "admin_activity_events" in inspect(c).get_table_names()
            assert {i["name"] for i in inspect(c).get_indexes("admin_activity_events")} != {
                f"ix_admin_activity_events_{field}" for field in ["actor_user_id","target_user_id","action","created_at"]}
            # This destructive recovery is allowed only in this isolated test,
            # after proving the partial new table has no events. Never automate
            # dropping a production history table to make a migration retry pass.
            assert c.scalar(text("SELECT COUNT(*) FROM admin_activity_events")) == 0
            c.execute(text("DROP TABLE admin_activity_events"))
            c.commit()
            monkeypatch.setattr(op, "create_index", original_index)
            command.upgrade(cfg, "0002")
            c.commit()
            command.check(cfg)
            assert c.scalar(text("SELECT full_name FROM users")) == "Preserved"
            assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
    finally:
        monkeypatch.setattr(op, "create_index", original_index)
        with engine.connect() as c:
            cfg.attributes["connection"] = c
            revision = c.scalar(text("SELECT version_num FROM alembic_version"))
            if revision == "0001" and "admin_activity_events" in inspect(c).get_table_names():
                assert c.scalar(text("SELECT COUNT(*) FROM admin_activity_events")) == 0
                c.execute(text("DROP TABLE admin_activity_events"))
                c.commit()
            command.downgrade(cfg, "base")
            c.execute(text("DROP TABLE alembic_version"))
            c.commit()
        engine.dispose()
