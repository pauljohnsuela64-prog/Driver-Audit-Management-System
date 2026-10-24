from unittest.mock import MagicMock

import pytest

from scripts import setup_database


@pytest.mark.parametrize("test", [False, True])
def test_provisioning_scoped_to_dams(monkeypatch, test):
    monkeypatch.setattr("sys.argv", ["setup_database"] + (["--test"] if test else []))
    monkeypatch.setattr("builtins.input", lambda _: "administrator")
    passwords = iter(["admin-test-only", "app-test-only", "migration-test-only"])
    monkeypatch.setattr(setup_database, "getpass", lambda _: next(passwords))
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = None
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(setup_database.pymysql, "connect", connect)
    setup_database.main()
    sql = [call.args[0] for call in cursor.execute.call_args_list]
    target = "driver_audit_test_phase1" if test else "driver_audit_db"
    assert any(f"CREATE DATABASE `{target}`" in statement for statement in sql)
    assert sum(statement.startswith("GRANT") for statement in sql) == 1
    assert not any("ALTER USER" in statement or "DROP" == statement.split()[0] for statement in sql)
    for statement in sql:
        assert "test-only" not in statement
    connection.close.assert_called_once()


def test_existing_database_is_never_modified(monkeypatch):
    monkeypatch.setattr("sys.argv", ["setup_database"])
    monkeypatch.setattr("builtins.input", lambda _: "administrator")
    passwords = iter(["admin-test-only", "app-test-only", "migration-test-only"])
    monkeypatch.setattr(setup_database, "getpass", lambda _: next(passwords))
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = ("driver_audit_db",)
    monkeypatch.setattr(setup_database.pymysql, "connect", lambda **kwargs: connection)
    with pytest.raises(SystemExit, match="already exists"):
        setup_database.main()
    assert cursor.execute.call_count == 1
    connection.close.assert_called_once()
