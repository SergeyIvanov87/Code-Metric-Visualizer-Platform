import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from interfaces.schema import RecordSchema
from interfaces_impl.access.mysql import MysqlAccessRecordEntry
from interfaces_impl.access.mysql.database import Base, initialize_schema


TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture()
def db_session():
    engine = create_engine(TEST_DATABASE_URL)
    testing_session = sessionmaker(
        autoflush=False,
        autocommit=False,
        bind=engine,
    )
    Base.metadata.create_all(bind=engine)
    db = testing_session()
    yield db
    db.close()


def _create_record(
    db_session,
    *,
    file_uri: str,
    offset: int,
    size: int,
    parent_id: int,
    metadata: dict | None = None,
    doc_type: str = "",
) -> RecordSchema:
    access = MysqlAccessRecordEntry(db_session)
    record_id = next(iter(access.create_unique_ids()))
    record = RecordSchema(
        file_uri=file_uri,
        id=record_id,
        offset=offset,
        size=size,
        parent_id=parent_id,
        metadata=metadata,
        doc_type=doc_type,
    )
    assert access.update_record_by_id(record_id, record) == 1
    return record


def test_create_record(db_session):
    record = _create_record(
        db_session,
        file_uri="/tmp/test.bin",
        offset=0,
        size=100,
        parent_id=0,
        metadata={"key": "value"},
        doc_type="txt",
    )

    assert record.id is not None
    assert record.file_uri == "/tmp/test.bin"
    assert record.doc_type == "txt"


def test_get_record(db_session):
    created = _create_record(
        db_session,
        file_uri="/tmp/file.bin",
        offset=0,
        size=123,
        parent_id=0,
    )

    fetched = MysqlAccessRecordEntry(db_session).get_records([created.id])

    assert len(fetched) == 1
    assert fetched[0].id == created.id


def test_update_record(db_session):
    created = _create_record(
        db_session,
        file_uri="/tmp/old.bin",
        offset=0,
        size=100,
        parent_id=0,
    )
    replacement = RecordSchema(
        file_uri=created.file_uri,
        id=created.id,
        offset=500,
        size=999,
        parent_id=123,
        doc_type="markdown",
    )
    access = MysqlAccessRecordEntry(db_session)

    assert access.update_record_by_id(created.id, replacement) == 1
    updated = access.get_records([created.id])[0]

    assert updated.offset == 500
    assert updated.size == 999
    assert updated.parent_id == 123
    assert updated.doc_type == "markdown"


def test_delete_record(db_session):
    created = _create_record(
        db_session,
        file_uri="/tmp/delete.bin",
        offset=0,
        size=100,
        parent_id=123,
    )
    access = MysqlAccessRecordEntry(db_session)

    deleted_count, missing_ids = access.delete_records(
        [created.id],
        cascade_delete=False,
    )

    assert deleted_count == 1
    assert missing_ids == []
    assert access.get_records([created.id]) == []


def test_create_records_by_ids(db_session):
    records = {
        10: RecordSchema(
            file_uri="/tmp/a.txt",
            id=10,
            offset=0,
            size=5,
            parent_id=10,
        ),
        11: RecordSchema(
            file_uri="/tmp/b.txt",
            id=11,
            offset=0,
            size=8,
            parent_id=11,
        ),
    }
    access = MysqlAccessRecordEntry(db_session)

    assert access.create_records_by_ids(records) == 2

    created = sorted(access.get_all_records(), key=lambda record: record.id)
    assert [record.id for record in created] == [10, 11]
    assert [record.size for record in created] == [5, 8]


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

    columns = {
        column["name"]
        for column in inspect(engine).get_columns("file_records")
    }
    assert "doc_type" in columns
