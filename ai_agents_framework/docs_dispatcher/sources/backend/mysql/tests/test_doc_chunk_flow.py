from __future__ import annotations

import io
from types import SimpleNamespace
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mysql.app.database import Base
from mysql.app.crud import create_file_record, get_all_records, get_file_record, update_file_record_ext
from mysql.doc_storage.operations import add_abstract_document, get_record, get_all_records as get_all_storage_records
from mysql.attach_doc_chunk import main as attach_chunk_main
from mysql.delete_doc import main as delete_doc_main


@pytest.fixture()
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture()
def db_session(db_engine):
    TestingSessionLocal = sessionmaker(
        autoflush=False,
        autocommit=False,
        bind=db_engine,
    )
    db = TestingSessionLocal()
    yield db
    db.close()


def _create_parent_document(db_session, storage_root: Path, file_name: str, content: str):
    parent = create_file_record(
        db_session,
        file_path=file_name,
        offset=0,
        size=len(content),
        parent_id=0,
        metadata_json={"kind": "document"},
    )
    storage_record = add_abstract_document(storage_root, Path(file_name), parent.id, content)
    storage_record.commit_doc(storage_root, offset=parent.offset)
    parent.parent_id = parent.id
    update_file_record_ext(db_session, parent.id, parent)
    return parent


def _mysql_backend_config(tmp_path: Path, storage_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        db_login_secret_path=tmp_path / "login",
        db_pwd_secret_path=tmp_path / "pwd",
        db_uri="sqlite:///ignored.db",
        storage_uri=storage_root,
    )


def test_attach_chunk_sets_parent_offset_and_size(monkeypatch, tmp_path, db_session, db_engine, capsys):
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    parent = _create_parent_document(db_session, storage_root, "parent.txt", "abcdefghij")

    metadata_path = tmp_path / "chunk_meta.json"
    metadata_path.write_text("chunk comment")

    monkeypatch.setattr("sys.stdin", io.BytesIO(b"defg"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "attach_doc_chunk.py",
            str(parent.id),
            "-m",
            str(metadata_path),
        ],
    )
    monkeypatch.setattr("mysql.attach_doc_chunk.load_mysql_backend_config", lambda: _mysql_backend_config(tmp_path, storage_root))
    monkeypatch.setattr("mysql.attach_doc_chunk.create_engine", lambda *args, **kwargs: db_engine)

    assert attach_chunk_main() == 0
    capsys.readouterr()

    records = get_all_records(db_session)
    assert len(records) == 2

    chunk = next(record for record in records if record.id != parent.id)
    assert chunk.parent_id == parent.id
    assert chunk.offset == 3
    assert chunk.size == 4
    assert chunk.file_path == parent.file_path
    assert chunk.metadata_json == {"comment": "chunk comment"}

    storage_chunk = get_record(storage_root, chunk.id)
    assert storage_chunk is not None
    assert storage_chunk.parent_id == parent.id
    assert storage_chunk.offset == 3
    assert storage_chunk.size == 4
    assert storage_chunk.metadata == {"comment": "chunk comment"}
    assert (storage_root / str(chunk.id) / "parent.storage_bin").read_bytes() == b""


def test_attach_chunk_rejects_missing_offset(monkeypatch, tmp_path, db_session, db_engine):
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    parent = _create_parent_document(db_session, storage_root, "parent.txt", "abcdefghij")

    metadata_path = tmp_path / "chunk_meta.json"
    metadata_path.write_text("chunk comment")

    monkeypatch.setattr("sys.stdin", io.BytesIO(b"not-found"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "attach_doc_chunk.py",
            str(parent.id),
            "-m",
            str(metadata_path),
        ],
    )
    monkeypatch.setattr("mysql.attach_doc_chunk.load_mysql_backend_config", lambda: _mysql_backend_config(tmp_path, storage_root))
    monkeypatch.setattr("mysql.attach_doc_chunk.create_engine", lambda *args, **kwargs: db_engine)

    assert attach_chunk_main() == -1


def test_delete_doc_removes_document_and_chunks(monkeypatch, tmp_path, db_session, db_engine):
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    parent = _create_parent_document(db_session, storage_root, "parent.txt", "abcdefghij")

    chunk_specs = [
        ("chunk_a.json", "chunk a", "abc"),
        ("chunk_b.json", "chunk b", "defg"),
    ]

    for meta_name, meta, chunk_data in chunk_specs:
        metadata_path = tmp_path / meta_name
        metadata_path.write_text(meta)
        monkeypatch.setattr("sys.stdin", io.BytesIO(chunk_data.encode("utf-8")))
        monkeypatch.setattr(
            "sys.argv",
            [
                "attach_doc_chunk.py",
                str(parent.id),
                "-m",
                str(metadata_path),
            ],
        )
        monkeypatch.setattr("mysql.attach_doc_chunk.load_mysql_backend_config", lambda: _mysql_backend_config(tmp_path, storage_root))
        monkeypatch.setattr("mysql.attach_doc_chunk.create_engine", lambda *args, **kwargs: db_engine)
        assert attach_chunk_main() == 0

    monkeypatch.setattr("sys.argv", [
        "delete_doc.py",
        str(parent.id),
    ])
    monkeypatch.setattr("mysql.delete_doc.load_mysql_backend_config", lambda: _mysql_backend_config(tmp_path, storage_root))
    monkeypatch.setattr("mysql.delete_doc.create_engine", lambda *args, **kwargs: db_engine)

    assert delete_doc_main() == 0

    assert get_all_records(db_session) == []
    assert get_all_storage_records(storage_root) == {}
