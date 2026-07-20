from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str):
    options = {}
    if database_url == "sqlite+pysqlite:///:memory:":
        options = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    return create_engine(database_url, **options)


def session_factory(engine):
    return lambda: Session(engine)
