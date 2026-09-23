from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mysql.app.crud import create_file_record, update_file_record
from mysql.app.database import Base
from mysql.read_id import read_ids


def _db_document(session, content: bytes):
    document = create_file_record(
        session,
        "/docs/document.txt",
        0,
        len(content),
        0,
        doc_type="txt",
    )
    return update_file_record(session, document.id, parent_id=document.id)


def _db_chunk(session, document_id: int, offset: int, size: int):
    return create_file_record(
        session,
        "/docs/document.txt",
        offset,
        size,
        document_id,
    )


def _storage_record(
    storage_uri: Path,
    record_id: int,
    parent_id: int,
    offset: int,
    size: int,
    payload: bytes = b"",
) -> None:
    record_dir = storage_uri / str(record_id)
    record_dir.mkdir()
    (record_dir / "document.txt.storage_bin").write_bytes(payload)
    (record_dir / "parentId").write_text(str(parent_id))
    (record_dir / "offset").write_text(str(offset))
    (record_dir / "size").write_text(str(size))
    (record_dir / "doc_type").write_text("txt" if parent_id == record_id else "")


def test_read_ids_reads_document_once_for_document_and_multiple_chunks(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    content = "start α chunk-one middle chunk-two end".encode("utf-8")
    first_chunk = "α chunk-one".encode("utf-8")
    second_chunk = "chunk-two".encode("utf-8")
    document = _db_document(session, content)
    db_only_chunk = _db_chunk(
        session,
        document.id,
        content.index(first_chunk),
        len(first_chunk),
    )
    storage_only_chunk_id = 100

    _storage_record(
        tmp_path,
        document.id,
        document.id,
        0,
        0,
        content,
    )
    _storage_record(
        tmp_path,
        storage_only_chunk_id,
        document.id,
        content.index(second_chunk),
        len(second_chunk),
    )

    payload_path = tmp_path / str(document.id) / "document.txt.storage_bin"
    original_read_bytes = Path.read_bytes
    payload_reads = 0

    def counted_read_bytes(path):
        nonlocal payload_reads
        if path == payload_path:
            payload_reads += 1
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)

    assert read_ids(
        session,
        tmp_path,
        [document.id, db_only_chunk.id, storage_only_chunk_id, document.id],
    ) == {
        document.id: {
            "id": document.id,
            "parent_id": document.id,
            "record_type": "document",
            "context": content.decode("utf-8"),
            "error_code": 0,
            "status": "success",
        },
        db_only_chunk.id: {
            "id": db_only_chunk.id,
            "parent_id": document.id,
            "record_type": "chunk",
            "context": first_chunk.decode("utf-8"),
            "error_code": 0,
            "status": "success",
        },
        storage_only_chunk_id: {
            "id": storage_only_chunk_id,
            "parent_id": document.id,
            "record_type": "chunk",
            "context": second_chunk.decode("utf-8"),
            "error_code": 0,
            "status": "success",
        },
    }
    assert payload_reads == 1

    session.close()


def test_read_ids_reports_missing_inconsistent_and_out_of_bounds_records(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    content = b"short document"
    document = _db_document(session, content)
    inconsistent_chunk = _db_chunk(session, document.id, 0, 5)
    out_of_bounds_id = 101

    _storage_record(
        tmp_path,
        document.id,
        document.id,
        0,
        len(content),
        content,
    )
    _storage_record(
        tmp_path,
        inconsistent_chunk.id,
        document.id,
        1,
        5,
    )
    _storage_record(
        tmp_path,
        out_of_bounds_id,
        document.id,
        len(content),
        1,
    )

    result = read_ids(session, tmp_path, [999, inconsistent_chunk.id, out_of_bounds_id])

    assert result[999] == {
        "id": 999,
        "error_code": -1,
        "status": "error",
        "error_msg": "Record id=999 does not exist",
    }
    assert result[inconsistent_chunk.id]["error_code"] == -1
    assert "inconsistent" in result[inconsistent_chunk.id]["error_msg"]
    assert result[out_of_bounds_id]["error_code"] == -1
    assert "exceeds parent document size" in result[out_of_bounds_id]["error_msg"]

    session.close()
