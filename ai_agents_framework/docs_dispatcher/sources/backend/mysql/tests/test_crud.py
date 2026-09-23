import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from mysql.app.database import Base, initialize_schema
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
        metadata_json={"key": "value"},
        doc_type="txt",
    )

    assert record.id is not None
    assert record.file_path == "/tmp/test.bin"
    assert record.doc_type == "txt"


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
        parent_id=123,
        doc_type="markdown",
    )

    assert updated.offset == 500
    assert updated.size == 999
    assert updated.parent_id == 123
    assert updated.doc_type == "markdown"


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


def test_initialize_schema_adds_doc_type_to_existing_table():
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE file_records ("
                "id INTEGER PRIMARY KEY, file_path VARCHAR(2048) NOT NULL, "
                "offset BIGINT NOT NULL, size BIGINT NOT NULL, parent_id BIGINT NOT NULL, "
                "metadata_json JSON)"
            )
        )

    initialize_schema(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("file_records")}
    assert "doc_type" in columns
