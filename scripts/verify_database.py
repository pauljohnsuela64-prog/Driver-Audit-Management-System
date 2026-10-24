"""Read-only check of connectivity, migration head, and schema compatibility."""
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.core.config import database_url
from backend.core.database import make_engine
from backend.models import Base


def main():
    engine = make_engine(database_url())
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
            if context.get_current_revision() != head:
                raise SystemExit("Migration version differs from repository head")
            if compare_metadata(context, Base.metadata):
                raise SystemExit("Database schema differs from model metadata")
            print(f"Connection OK; migration {head}; schema compatible")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except SQLAlchemyError:
        raise SystemExit("Database verification failed; check dedicated DAMS configuration and server availability") from None
