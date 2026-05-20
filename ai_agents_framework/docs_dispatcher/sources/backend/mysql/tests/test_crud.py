import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mysql.app.database import Base
from mysql.app.models import FileRecord
from mysql.app.crud import (
    create_file_record,
    get_file_record,
    update_file_record,
    delete_file_record
)
from mysql.app.rebuild import rebuild_table_from_directory


TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture()
def db_session():

    engine = create_engine(TEST_DATABASE_URL)

    TestingSessionLocal = sessionmaker(
        autoflush=False,
        autocommit=False,
        bind=engine
    )

    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    yield db

    db.close()


def test_create_record(db_session):

    record = create_file_record(
        db_session,
        file_path="/tmp/test.bin",
        offset=0,
        size=100,
        parent_id = 0,
        metadata_json={"key": "value"}
    )

    assert record.id is not None
    assert record.file_path == "/tmp/test.bin"


def test_get_record(db_session):

    created = create_file_record(
        db_session,
        file_path="/tmp/file.bin",
        offset=0,
        size=123,
        parent_id = 0,
    )

    fetched = get_file_record(db_session, created.id)

    assert fetched is not None
    assert fetched.id == created.id


def test_update_record(db_session):

    created = create_file_record(
        db_session,
        file_path="/tmp/old.bin",
        offset=0,
        size=100,
        parent_id = 0
    )

    updated = update_file_record(
        db_session,
        created.id,
        offset=500,
        size=999,
        parent_id = 123
    )

    assert updated.offset == 500
    assert updated.size == 999
    assert updated.parent_id == 123


def test_delete_record(db_session):

    created = create_file_record(
        db_session,
        file_path="/tmp/delete.bin",
        offset=0,
        size=100,
        parent_id = 123,
    )

    result = delete_file_record(
        db_session,
        created.id
    )

    assert result is True

    deleted = get_file_record(
        db_session,
        created.id
    )

    assert deleted is None


def test_rebuild_table_from_directory(db_session):

    with tempfile.TemporaryDirectory() as tmpdir:

        file1 = Path(tmpdir) / "a.txt"
        file2 = Path(tmpdir) / "b.txt"

        file1.write_text("hello")
        file2.write_text("world!!!")

        rebuild_table_from_directory(
            db_session,
            tmpdir
        )

        records = db_session.query(FileRecord).all()

        assert len(records) == 2

        sizes = sorted([r.size for r in records])

        assert sizes == [5, 8]

        for record in records:
            assert record.offset == 0
