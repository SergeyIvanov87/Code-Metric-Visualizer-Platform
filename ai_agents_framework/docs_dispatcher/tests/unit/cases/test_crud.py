from interfaces_impl.access.mysql import MysqlAccessRecordEntry
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from interfaces_impl.access.mysql.database import Base, initialize_schema
from interfaces_impl.access.mysql.models import FileRecord




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

    record = MysqlAccessRecordEntry(db_session).create_file_record(file_path='/tmp/test.bin', offset=0, size=100, parent_id=0, metadata_json={'key': 'value'}, doc_type='txt')

    assert record.id is not None
    assert record.file_path == "/tmp/test.bin"
    assert record.doc_type == "txt"


def test_get_record(db_session):

    created = MysqlAccessRecordEntry(db_session).create_file_record(file_path='/tmp/file.bin', offset=0, size=123, parent_id=0)

    fetched = MysqlAccessRecordEntry(db_session).get_file_record(created.id)

    assert fetched is not None
    assert fetched.id == created.id


def test_update_record(db_session):

    created = MysqlAccessRecordEntry(db_session).create_file_record(file_path='/tmp/old.bin', offset=0, size=100, parent_id=0)

    updated = MysqlAccessRecordEntry(db_session).update_file_record(created.id, offset=500, size=999, parent_id=123, doc_type='markdown')

    assert updated.offset == 500
    assert updated.size == 999
    assert updated.parent_id == 123
    assert updated.doc_type == "markdown"


def test_delete_record(db_session):

    created = MysqlAccessRecordEntry(db_session).create_file_record(file_path='/tmp/delete.bin', offset=0, size=100, parent_id=123)

    access = MysqlAccessRecordEntry(db_session)
    deleted_count, missing_ids = access.delete_records([created.id], cascade_delete=False)

    assert deleted_count == 1
    assert missing_ids == []
    assert access.get_records([created.id]) == []


def test_rebuild_table_from_directory(db_session):

    with tempfile.TemporaryDirectory() as tmpdir:

        file1 = Path(tmpdir) / "a.txt"
        file2 = Path(tmpdir) / "b.txt"

        file1.write_text("hello")
        file2.write_text("world!!!")

        MysqlAccessRecordEntry(db_session).rebuild_table_from_directory(tmpdir)

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
