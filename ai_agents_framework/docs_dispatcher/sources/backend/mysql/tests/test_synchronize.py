from pathlib import Path

import json
import pytest
import sys
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from mysql.app.database import Base
from mysql.app.models import FileRecord
from mysql.app.crud import (
    create_file_record,
    create_file_record_ext,
    get_file_record,
    get_all_records,
    update_file_record,
    delete_file_record
)

from mysql.synchronize_data import synchronize_records
from mysql.doc_storage.models import StorageRecord

TEST_DATABASE_URL = "sqlite:///:memory:"

stub_db_data = {"equal" : FileRecord(id=10, file_path="file_id_10", offset=0, size=1000,parent_id=10),
                "id_mismatch" : FileRecord(id=1000, file_path="file_id_1000", offset=0, size=1000,parent_id=10),
                "id_absent" : FileRecord(id=3000, file_path="file_id_3000", offset=0, size=1000,parent_id=10),
                "offset_to_fix" : FileRecord(id=11, file_path="file_id_11", offset=3000, size=1000,parent_id=10),
                "size_to_fix" : FileRecord(id=12, file_path="file_id_12", offset=0, size=3000,parent_id=10),
                }

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
    global stub_db_data
    stmt = select(FileRecord)

    for user in db.scalars(stmt):
        print(user, flush = True)

    for req in stub_db_data.values():
        create_file_record_ext(db, req)
    yield db

    db.close()

def convert_to_StorageRecord(req_name, db_record: FileRecord):
    ret = StorageRecord(file_uri = db_record.file_path, unique_id = db_record.id, offset = db_record.offset, size = db_record.size, parent_id = db_record.parent_id, metadata = db_record.metadata_json)
    if req_name == "id_mismatch":
        ret.unique_id = db_record.id * 98765431
    if req_name == "id_absent":
        ret = {}
    if req_name == "offset_to_fix":
        ret.offset = db_record.offset + 100
    if req_name == "size_to_fix":
        ret.size = db_record.size + 100
    return ret

def test_amend_db_records(db_session):
    all_storage_records = { req.id: convert_to_StorageRecord(name, req) for name, req in stub_db_data.items() if convert_to_StorageRecord(name, req) != {}}
    new_added_id = 9999
    all_storage_records[new_added_id] = StorageRecord(file_uri=f"file_id_{new_added_id}", unique_id = new_added_id, offset = 0, size=new_added_id, parent_id = new_added_id)
    all_db_records = get_all_records(db_session)
    synchronize_records(db_session, all_db_records, all_storage_records)

    updated_db_records = get_all_records(db_session)
    sorted_updated_db_records = sorted(updated_db_records, key = lambda x : x.id)

    assert len(updated_db_records) == len(all_storage_records), "sizes of colelctions must be equal"
    for db_record, (storage_record_id, storage_record_data) in zip(updated_db_records, dict(sorted(all_storage_records.items())).items()):
        assert db_record.id == storage_record_id, "Unique Ids must be equal"
        assert db_record.file_path == storage_record_data.file_uri, "File URI and path must be equal"
        assert db_record.offset == storage_record_data.offset, "Offsets must be equal"
        assert db_record.size == storage_record_data.size, "Sized must be equal"
        assert db_record.parent_id == storage_record_data.parent_id, "Parent Ids must be equal"
        # assert db_record.metadata_json == storage_record_data.metadata, "Metadatas must be equal"
