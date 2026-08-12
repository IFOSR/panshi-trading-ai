from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import StaticPool
from sqlalchemy import event


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str):
    options = {}
    if database_url == "sqlite+pysqlite:///:memory:":
        options = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    engine = create_engine(database_url, **options)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def session_factory(engine):
    return lambda: Session(engine)
