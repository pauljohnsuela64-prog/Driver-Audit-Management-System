from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData, create_engine, event
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.types import TypeDecorator
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement

NAMING = {"ix": "ix_%(table_name)s_%(column_0_name)s",
          "uq": "uq_%(table_name)s_%(column_0_name)s",
          "ck": "ck_%(table_name)s_%(constraint_name)s",
          "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
          "pk": "pk_%(table_name)s"}


def utcnow():
    return datetime.now(timezone.utc)


class UTCNow(FunctionElement):
    type = DateTime()
    inherit_cache = True


@compiles(UTCNow)
def compile_now(element, compiler, **kwargs):
    return "CURRENT_TIMESTAMP"


@compiles(UTCNow, "mysql")
def compile_mysql_now(element, compiler, **kwargs):
    return "CURRENT_TIMESTAMP(6)"


class UTCDateTime(TypeDecorator):
    """Store naive UTC, return aware UTC; reject ambiguous naive inputs."""
    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(DATETIME(fsp=6) if dialect.name == "mysql" else DateTime())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def make_engine(url):
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
    if engine.dialect.name == "mysql":
        @event.listens_for(engine, "connect")
        def configure_mysql(connection, record):
            with connection.cursor() as cursor:
                cursor.execute("SET time_zone = '+00:00'")
                cursor.execute("SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'")
    elif engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
    return engine


@contextmanager
def session_scope(engine):
    with Session(engine) as session:
        with session.begin():
            yield session
