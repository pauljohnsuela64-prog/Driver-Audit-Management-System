"""Live-only checks for MySQL isolation and least-privilege runtime access."""
import os
from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.core.database import make_engine, utcnow
from backend.models import AdminActivityEvent, AuditEvent, AuthSession, User
from tests.mysql_support import mysql_test_engine
from tests.test_foundation import audit, user

pytestmark = pytest.mark.mysql


@pytest.fixture
def live_database():
    if not os.getenv('DAMS_TEST_DATABASE_URL'):
        pytest.skip('DAMS_TEST_DATABASE_URL absent; live MySQL required')
    engine = mysql_test_engine()
    config = Config('alembic.ini')
    try:
        with engine.connect() as connection:
            config.attributes['connection'] = connection
            command.upgrade(config, 'head')
        yield engine
    finally:
        try:
            with engine.connect() as connection:
                config.attributes['connection'] = connection
                command.downgrade(config, 'base')
                connection.execute(text('DROP TABLE alembic_version'))
                connection.commit()
        finally:
            engine.dispose()


def test_mysql_repeatable_read_and_rollback(live_database):
    with live_database.connect() as writer, live_database.connect().execution_options(isolation_level='REPEATABLE READ') as reader:
        assert reader.scalar(text('SELECT @@session.transaction_isolation')) == 'REPEATABLE-READ'
        assert reader.scalar(text('SELECT COUNT(*) FROM users')) == 0
        writer.execute(text("INSERT INTO users (username, full_name, password_hash, role) VALUES ('isolation', 'Test', 'test-only', 'AUDITOR')"))
        # A second connection must not see uncommitted writes.
        assert reader.scalar(text('SELECT COUNT(*) FROM users')) == 0
        writer.commit()
        # The established repeatable-read snapshot remains stable after commit.
        assert reader.scalar(text('SELECT COUNT(*) FROM users')) == 0
        reader.commit()
        assert reader.scalar(text('SELECT COUNT(*) FROM users')) == 1
        writer.execute(text("UPDATE users SET full_name='rolled back' WHERE username='isolation'"))
        writer.rollback()
        reader.commit()
        assert reader.scalar(text("SELECT full_name FROM users WHERE username='isolation'")) == 'Test'


def test_mysql_runtime_permissions(live_database):
    value = os.getenv('DAMS_TEST_RUNTIME_URL')
    if not value:
        pytest.skip('DAMS_TEST_RUNTIME_URL absent; runtime grants require dedicated credentials')
    url = make_url(value)
    target = live_database.url
    if (url.drivername != target.drivername or url.host != target.host
            or url.port != target.port or url.database != target.database
            or url.username != 'dams_test_app' or not url.password
            or set(url.query) - {'charset'}
            or url.query.get('charset', 'utf8mb4') != 'utf8mb4'):
        raise ValueError('Runtime URL must use dams_test_app on the same isolated test target')
    runtime = make_engine(url)
    try:
        with Session(runtime) as session:
            actor = user()
            session.add(actor)
            session.flush()
            record = audit(actor.id)
            session.add(record)
            session.flush()
            event = AuditEvent(audit_id=record.id, actor_user_id=actor.id, action='CREATE')
            token = AuthSession(user_id=actor.id, token_hash='b' * 64, expires_at=utcnow() + timedelta(hours=1))
            session.add_all([event, token])
            session.add(AdminActivityEvent(actor_user_id=actor.id, target_user_id=actor.id, action="CREATE"))
            session.commit()
            actor.full_name = 'Updated test auditor'
            record.remarks = 'Allowed runtime update'
            token.revoked_at = utcnow()
            session.commit()
            assert session.scalar(select(User.full_name)) == 'Updated test auditor'
            actor.full_name = 'Must roll back'
            session.flush()
            session.rollback()
            assert session.scalar(select(User.full_name)) == 'Updated test auditor'
        denied = [
            'DELETE FROM users WHERE 1=0',
            'DELETE FROM audit_records WHERE 1=0',
            'DELETE FROM auth_sessions WHERE 1=0',
            'DELETE FROM audit_events WHERE 1=0',
            'DELETE FROM admin_activity_events WHERE 1=0',
            "UPDATE admin_activity_events SET action='CREATE' WHERE 1=0",
            "UPDATE audit_events SET action='UPDATE' WHERE 1=0",
            'CREATE TABLE runtime_ddl_probe (id INT PRIMARY KEY)',
            # This existing system table makes denial meaningful on a disposable
            # server without requiring a production-named database or any grants.
            'SELECT * FROM mysql.user LIMIT 0',
        ]
        for statement in denied:
            with runtime.connect() as connection:
                with pytest.raises(DBAPIError) as failure:
                    connection.execute(text(statement))
                assert failure.value.orig.args[0] in {1044, 1142, 1143}
    finally:
        runtime.dispose()
