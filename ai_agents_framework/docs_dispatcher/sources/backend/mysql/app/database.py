from pathlib import Path
from typing import overload

from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


@overload
def create_engine(db_uri: str) -> Engine:
    ...


@overload
def create_engine(
    login_secret_path: Path,
    pwd_secret_path: Path,
    db_uri: str,
) -> Engine:
    ...


def create_engine(*args) -> Engine:
    if len(args) == 1:
        (db_uri,) = args
        return sa_create_engine(
            db_uri,
            echo=False,
            pool_pre_ping=True,
        )

    if len(args) == 3:
        login_secret_path, pwd_secret_path, db_uri = args
        with Path(login_secret_path).open() as login_file:
            login = login_file.read().strip()
        with Path(pwd_secret_path).open() as pwd_file:
            password = pwd_file.read().strip()

        full_db_uri = f"mysql+pymysql://{login}:{password}@{db_uri}"
        return sa_create_engine(
            full_db_uri,
            echo=False,
            pool_pre_ping=True,
        )

    raise TypeError("create_engine expects either 1 or 3 positional arguments")

def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        autoflush=False,
        autocommit=False,
        bind=engine,
    )


def create_session(engine: Engine) -> Session:
    return create_session_factory(engine)()


class Base(DeclarativeBase):
    pass
