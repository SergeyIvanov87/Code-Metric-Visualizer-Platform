from interfaces_impl.store.persistent import PersistentStorageRecordEntry
from interfaces_impl.access.mysql import MysqlAccessRecordEntry
from interfaces.schema import RecordSchema
from mysql_persistent.backend import MysqlPersistentBackend
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


from interfaces_impl.access.mysql.database import Base



def _db_document(session, doc_id: int, file_uri: str, doc_type: str = "txt"):
    access = MysqlAccessRecordEntry(session)
    record_id = next(iter(access.create_unique_ids()))
    assert record_id == doc_id
    document = RecordSchema(
        file_uri=file_uri,
        id=record_id,
        offset=0,
        size=10,
        parent_id=record_id,
        doc_type=doc_type,
    )
    assert access.update_record_by_id(record_id, document) == 1
    return document


def _db_chunk(session, document_id: int, file_uri: str):
    access = MysqlAccessRecordEntry(session)
    record_id = next(iter(access.create_unique_ids()))
    chunk = RecordSchema(
        file_uri=file_uri,
        id=record_id,
        offset=0,
        size=5,
        parent_id=document_id,
    )
    assert access.update_record_by_id(record_id, chunk) == 1
    return chunk


def _storage_record(
    storage_uri: Path,
    record_id: int,
    parent_id: int,
    file_uri: str,
    doc_type: str = "",
) -> None:
    record_dir = storage_uri / str(record_id)
    record_dir.mkdir()
    (record_dir / f"{file_uri}.storage_bin").touch()
    (record_dir / "parentId").write_text(str(parent_id))
    (record_dir / "offset").write_text("0")
    (record_dir / "size").write_text("0")
    (record_dir / "doc_type").write_text(doc_type)


def test_get_document_info_reports_complete_partial_and_absent_documents(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    complete = _db_document(session, 1, "%slash%docs%slash%complete.txt", "markdown")
    complete_chunk = _db_chunk(session, complete.id, complete.file_uri)
    db_only = _db_document(session, 3, "%slash%docs%slash%db-only.txt")
    db_only_chunk = _db_chunk(session, db_only.id, db_only.file_uri)

    _storage_record(tmp_path, complete.id, complete.id, "%slash%docs%slash%complete.txt", "markdown")
    _storage_record(tmp_path, complete_chunk.id, complete.id, "%slash%docs%slash%complete.txt")
    _storage_record(tmp_path, 5, 5, "%slash%docs%slash%storage-only.txt", "pdf")
    _storage_record(tmp_path, 6, 5, "%slash%docs%slash%storage-only.txt")

    backend = MysqlPersistentBackend(
        access=MysqlAccessRecordEntry(session),
        store=PersistentStorageRecordEntry(tmp_path),
    )
    assert backend.get_document_info([1, 3, 5, 99, 1]) == {
        "found": [1],
        "inconsistent": [3, 5],
        "not_found": [99],
        "1": {
            "error_code": 0,
            "status": "success",
            "info": {
                "file_uri": "/docs/complete.txt",
                "type": "markdown",
                "chunks": [complete_chunk.id],
            },
        },
        "3": {
            "error_code": 1,
            "status": "Not found in the doc storage: file storage",
            "info": {
                "file_uri": "/docs/db-only.txt",
                "type": "txt",
                "chunks": [db_only_chunk.id],
            },
        },
        "5": {
            "error_code": 1,
            "status": "Not found in the doc storage: database",
            "info": {
                "file_uri": "/docs/storage-only.txt",
                "type": "pdf",
                "chunks": [6],
            },
        },
        "99": {
            "error_code": -1,
            "status": "The doc is absent or ID is incorrect",
        },
    }

    session.close()


def test_chunk_id_is_not_mistaken_for_a_document(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    document = _db_document(session, 1, "/docs/document.txt")
    chunk = _db_chunk(session, document.id, document.file_uri)
    _storage_record(tmp_path, chunk.id, document.id, "chunk.txt")

    backend = MysqlPersistentBackend(
        access=MysqlAccessRecordEntry(session),
        store=PersistentStorageRecordEntry(tmp_path),
    )
    assert backend.get_document_info([chunk.id]) == {
        "found": [],
        "inconsistent": [],
        "not_found": [chunk.id],
        str(chunk.id): {
            "error_code": -1,
            "status": "The doc is absent or ID is incorrect",
        },
    }

    session.close()
