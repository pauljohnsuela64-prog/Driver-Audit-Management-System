import pytest
from sqlalchemy.orm import Session

from backend.core.database import make_engine
from backend.models import Base


@pytest.fixture
def engine():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session
