from dataclasses import replace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from interfaces.schema import RecordSchema
from interfaces_impl.access.mysql import MysqlAccessRecordEntry
from interfaces_impl.access.mysql.database import Base
from interfaces_impl.store.persistent import PersistentStorageRecordEntry
from mysql_persistent.backend import MysqlPersistentBackend


TEST_DATABASE_URL = "sqlite:///:memory:"

STUB_DB_DATA = {
    "equal": RecordSchema(
        file_uri="file_id_10",
        id=10,
        offset=0,
        size=1000,
        parent_id=10,
        doc_type="txt",
    ),
    "id_mismatch": RecordSchema(
        file_uri="file_id_1000",
        id=1000,
        offset=0,
        size=1000,
        parent_id=10,
        doc_type="txt",
    ),
    "id_absent": RecordSchema(
        file_uri="file_id_3000",
        id=3000,
        offset=0,
        size=1000,
        parent_id=10,
        doc_type="txt",
    ),
    "offset_to_fix": RecordSchema(
        file_uri="file_id_11",
        id=11,
        offset=3000,
        size=1000,
        parent_id=10,
        doc_type="txt",
    ),
    "size_to_fix": RecordSchema(
        file_uri="file_id_12",
        id=12,
        offset=0,
        size=3000,
        parent_id=10,
        doc_type="txt",
    ),
}


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
    MysqlAccessRecordEntry(db).create_records_by_ids(
        {record.id: record for record in STUB_DB_DATA.values()}
    )
    yield db
    db.close()


def _storage_version(name: str, db_record: RecordSchema) -> RecordSchema | None:
    if name == "id_mismatch":
        new_id = db_record.id * 98765431
        return replace(db_record, id=new_id)
    if name == "id_absent":
        return None
    if name == "offset_to_fix":
        return replace(db_record, offset=db_record.offset + 100)
    if name == "size_to_fix":
        return replace(db_record, size=db_record.size + 100)
    return replace(db_record)


def _write_storage_record(storage_root, record: RecordSchema) -> None:
    record_dir = storage_root / str(record.id)
    record_dir.mkdir()
    (record_dir / f"{record.file_uri}.storage_bin").touch()
    (record_dir / "parentId").write_text(str(record.parent_id))
    (record_dir / "offset").write_text(str(record.offset))
    (record_dir / "size").write_text(str(record.size))
    (record_dir / "doc_type").write_text(record.doc_type)
    metadata = (record.metadata or {}).get("comment")
    if metadata is not None:
        (record_dir / "metadata").write_text(metadata)


def test_amend_db_records(db_session, tmp_path):
    storage_records = {}
    for name, db_record in STUB_DB_DATA.items():
        storage_record = _storage_version(name, db_record)
        if storage_record is not None:
            storage_records[storage_record.id] = storage_record

    new_added_id = 9999
    storage_records[new_added_id] = RecordSchema(
        file_uri=f"file_id_{new_added_id}",
        id=new_added_id,
        offset=0,
        size=new_added_id,
        parent_id=new_added_id,
        metadata={"comment": "new"},
        doc_type="pdf",
    )
    for storage_record in storage_records.values():
        _write_storage_record(tmp_path, storage_record)

    backend = MysqlPersistentBackend(
        access=MysqlAccessRecordEntry(db_session),
        store=PersistentStorageRecordEntry(tmp_path),
    )
    assert backend.synchronize() == {
        "created": 2,
        "updated": 2,
        "deleted": 2,
        "not_changed": 1,
        "initial DB records": 5,
        "storage size": 5,
    }

    updated_db_records = {
        record.id: record
        for record in MysqlAccessRecordEntry(db_session).get_all_records()
    }
    assert set(updated_db_records) == set(storage_records)
    for record_id, storage_record in storage_records.items():
        assert updated_db_records[record_id].get_difference(storage_record) == {}


def test_synchronize_updates_doc_type(tmp_path):
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    access = MysqlAccessRecordEntry(session)
    db_record = RecordSchema(
        file_uri="document.txt",
        id=1,
        offset=0,
        size=10,
        parent_id=1,
        doc_type="txt",
    )
    access.create_records_by_ids({1: db_record})
    storage_record = replace(db_record, doc_type="markdown")
    _write_storage_record(tmp_path, storage_record)

    backend = MysqlPersistentBackend(
        access=access,
        store=PersistentStorageRecordEntry(tmp_path),
    )
    result = backend.synchronize()

    assert result["updated"] == 1
    assert access.get_records([1])[0].doc_type == "markdown"
    session.close()
