from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mysql.app.crud import create_file_record, update_file_record
from mysql.app.database import Base
from mysql.get_doc_info import get_document_info


def _db_document(session, doc_id: int, file_uri: str, doc_type: str = "txt"):
    document = create_file_record(session, file_uri, 0, 10, 0, doc_type=doc_type)
    assert document.id == doc_id
    return update_file_record(session, document.id, parent_id=document.id)


def _db_chunk(session, document_id: int, file_uri: str):
    return create_file_record(session, file_uri, 0, 5, document_id)


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
    complete_chunk = _db_chunk(session, complete.id, complete.file_path)
    db_only = _db_document(session, 3, "%slash%docs%slash%db-only.txt")
    db_only_chunk = _db_chunk(session, db_only.id, db_only.file_path)

    _storage_record(tmp_path, complete.id, complete.id, "%slash%docs%slash%complete.txt", "markdown")
    _storage_record(tmp_path, complete_chunk.id, complete.id, "%slash%docs%slash%complete.txt")
    _storage_record(tmp_path, 5, 5, "%slash%docs%slash%storage-only.txt", "pdf")
    _storage_record(tmp_path, 6, 5, "%slash%docs%slash%storage-only.txt")

    assert get_document_info(session, tmp_path, [1, 3, 5, 99, 1]) == {
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
    chunk = _db_chunk(session, document.id, document.file_path)
    _storage_record(tmp_path, chunk.id, document.id, "chunk.txt")

    assert get_document_info(session, tmp_path, [chunk.id]) == {
        "found": [],
        "inconsistent": [],
        "not_found": [chunk.id],
        str(chunk.id): {
            "error_code": -1,
            "status": "The doc is absent or ID is incorrect",
        },
    }

    session.close()
