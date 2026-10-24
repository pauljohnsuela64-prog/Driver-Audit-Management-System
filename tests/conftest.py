import pytest
from sqlalchemy.orm import Session
from sqlalchemy import text
from alembic import command
from alembic.config import Config

from backend.core.database import make_engine
from backend.models import Base
from tests.mysql_support import mysql_test_engine


def pytest_addoption(parser):
    parser.addoption("--mysql", action="store_true", help="Run model/transaction tests against the dedicated disposable MySQL database")


@pytest.fixture
def engine(request):
    live_mysql = request.config.getoption("--mysql")
    engine = mysql_test_engine() if live_mysql else make_engine("sqlite://")
    config = Config("alembic.ini")
    try:
        if live_mysql:
            with engine.connect() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
        else:
            Base.metadata.create_all(engine)
        yield engine
    finally:
        if live_mysql:
            with engine.connect() as connection:
                config.attributes["connection"] = connection
                command.downgrade(config, "base")
                connection.execute(text("DROP TABLE alembic_version"))
                connection.commit()
        engine.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session
