from unittest.mock import MagicMock

import pytest

from tests import mysql_support


@pytest.mark.parametrize("value", ["", "sqlite://", "mysql+pymysql://dams:dummy@localhost/driver_audit_db", "mysql+pymysql://root:dummy@localhost/driver_audit_test_phase1", "mysql+pymysql://dams@localhost/driver_audit_test_phase1"])
def test_mysql_guard_rejects_target_before_connection(monkeypatch, value):
    monkeypatch.setenv("DAMS_TEST_DATABASE_URL", value)
    connect = MagicMock()
    monkeypatch.setattr(mysql_support, "make_engine", connect)
    with pytest.raises(ValueError):
        mysql_support.mysql_test_engine()
    connect.assert_not_called()


def test_mysql_guard_preserves_existing_tables(monkeypatch):
    monkeypatch.setenv("DAMS_TEST_DATABASE_URL", "mysql+pymysql://dams:dummy@localhost/driver_audit_test_phase1")
    engine = MagicMock()
    monkeypatch.setattr(mysql_support, "make_engine", lambda _: engine)
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["existing_work"]
    monkeypatch.setattr(mysql_support, "inspect", lambda _: inspector)
    with pytest.raises(ValueError, match="refusing"):
        mysql_support.mysql_test_engine()
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("query", ["user=root", "database=driver_audit_db", "host=other", "charset=latin1"])
def test_mysql_guard_rejects_connection_overrides(monkeypatch, query):
    monkeypatch.setenv("DAMS_TEST_DATABASE_URL", "mysql+pymysql://dams:dummy@localhost/driver_audit_test_phase1?" + query)
    connect = MagicMock()
    monkeypatch.setattr(mysql_support, "make_engine", connect)
    with pytest.raises(ValueError):
        mysql_support.mysql_test_engine()
    connect.assert_not_called()
