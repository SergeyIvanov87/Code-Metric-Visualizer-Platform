from __future__ import annotations
from interfaces_impl.store.persistent import PersistentStorageRecordEntry
from interfaces import RuntimeConfig
from mysql_persistent.backend import MysqlPersistentBackend

import io
from contextlib import nullcontext
from interfaces_impl.access.mysql import MysqlAccessRecordEntry
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from interfaces_impl.access.mysql.database import Base


from attach_doc_chunk import main as attach_chunk_main
from delete_doc import main as delete_doc_main
from put_doc import main as put_doc_main


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
    access = MysqlAccessRecordEntry(db_session)
    backend = MysqlPersistentBackend(
        access=access,
        store=PersistentStorageRecordEntry(storage_root),
    )
    parent_id = backend.put_doc_by_data(
        Path(file_name),
        content.encode("utf-8"),
        metadata_text="document metadata",
        doc_type="txt",
    )["unique_id"]
    return access.get_records([parent_id])[0]


def _mysql_backend_config(tmp_path: Path, storage_root: Path) -> RuntimeConfig:
    return RuntimeConfig(options={"storage_uri": str(storage_root)}, spec_path=tmp_path / "current")



def test_document_storage_round_trips_metadata_and_doc_type(
    monkeypatch,
    tmp_path,
    db_session,
    capsys,
):
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    monkeypatch.setattr("sys.stdin", io.BytesIO(b"abcdefghij"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "put_doc.py",
            "-metadata",
            "document metadata",
            "-doc_type",
            "txt",
        ],
    )
    monkeypatch.setattr(
        "backend.dispatcher.runtime.load_runtime_config",
        lambda config=None: _mysql_backend_config(tmp_path, storage_root),
    )
    monkeypatch.setattr(
        "interfaces_impl.access.mysql.MysqlAccessRecordEntry.create_instance",
        lambda config: nullcontext(MysqlAccessRecordEntry(db_session)),
    )

    assert put_doc_main() == 0
    result = json.loads(capsys.readouterr().out)
    parent_id = int(result["unique_id"])

    access = MysqlAccessRecordEntry(db_session)
    records = access.get_all_records()
    assert {int(record.id) for record in records} == {parent_id}

    store = PersistentStorageRecordEntry(storage_root)
    storage_record = store.get_records([parent_id])[0]
    assert storage_record.metadata == {"comment": "document metadata"}
    assert storage_record.doc_type == "txt"
    assert (
        storage_root / str(parent_id) / "metadata"
    ).read_text() == "document metadata"
    assert (storage_root / str(parent_id) / "doc_type").read_text() == "txt"

    uri_path = tmp_path / "uri_document.txt"
    uri_payload = " \n\tURI документ\u2003\n".encode("utf-8")
    uri_path.write_bytes(uri_payload)
    monkeypatch.setattr(
        "sys.argv",
        [
            "put_doc.py",
            "-URI",
            str(uri_path),
            "-doc_type",
            "txt",
        ],
    )

    assert put_doc_main() == 0
    uri_result = json.loads(capsys.readouterr().out)
    uri_id = int(uri_result["unique_id"])
    assert uri_path.read_bytes() == uri_payload
    uri_record = PersistentStorageRecordEntry(storage_root).get_records([uri_id])[0]
    expected_payload = uri_payload
    assert PersistentStorageRecordEntry(storage_root).read_record_data(uri_record) == expected_payload
    assert uri_record.size == len(expected_payload)
    assert access.get_records([uri_id])[0].size == len(expected_payload)
    assert {int(record.id) for record in access.get_all_records()} == {
        parent_id,
        uri_id,
    }

    def fail_after_payload_write(record_entry, **fields):
        raise RuntimeError("simulated storage failure")

    monkeypatch.setattr(
        PersistentStorageRecordEntry,
        "write_fields",
        fail_after_payload_write,
    )
    backend = MysqlPersistentBackend(access=access, store=store)

    with pytest.raises(RuntimeError, match="simulated storage failure"):
        backend.put_doc_by_data(Path("failed.txt"), b"failed data")

    assert {int(record.id) for record in access.get_all_records()} == {
        parent_id,
        uri_id,
    }
    assert set(store.get_all_records()) == {parent_id, uri_id}


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
            "-doc_id", str(parent.id),
            "-metadata",
            str(metadata_path),
        ],
    )
    monkeypatch.setattr("backend.dispatcher.runtime.load_runtime_config", lambda config=None: _mysql_backend_config(tmp_path, storage_root))
    monkeypatch.setattr("interfaces_impl.access.mysql.MysqlAccessRecordEntry.create_instance", lambda config: nullcontext(MysqlAccessRecordEntry(db_session)))

    assert attach_chunk_main() == 0
    capsys.readouterr()

    records = MysqlAccessRecordEntry(db_session).get_all_records()
    assert len(records) == 2

    chunk = next(record for record in records if record.id != parent.id)
    assert chunk.parent_id == parent.id
    assert chunk.offset == 3
    assert chunk.size == 4
    assert chunk.file_uri == parent.file_uri
    assert chunk.metadata == {"comment": "chunk comment"}

    storage_chunk = PersistentStorageRecordEntry(storage_root).get_records(
        [chunk.id]
    )[0]
    assert storage_chunk is not None
    assert storage_chunk.parent_id == parent.id
    assert storage_chunk.offset == 3
    assert storage_chunk.size == 4
    assert storage_chunk.metadata == {"comment": "chunk comment"}
    assert (storage_root / str(chunk.id) / "parent.txt.storage_bin").read_bytes() == b""


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
            "-doc_id", str(parent.id),
            "-metadata",
            str(metadata_path),
        ],
    )
    monkeypatch.setattr("backend.dispatcher.runtime.load_runtime_config", lambda config=None: _mysql_backend_config(tmp_path, storage_root))
    monkeypatch.setattr("interfaces_impl.access.mysql.MysqlAccessRecordEntry.create_instance", lambda config: nullcontext(MysqlAccessRecordEntry(db_session)))

    assert attach_chunk_main() == -1


def test_delete_doc_removes_multiple_documents_and_chunks(
    monkeypatch,
    tmp_path,
    db_session,
    db_engine,
    capsys,
):
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
                "-doc_id", str(parent.id),
                "-metadata",
                str(metadata_path),
            ],
        )
        monkeypatch.setattr("backend.dispatcher.runtime.load_runtime_config", lambda config=None: _mysql_backend_config(tmp_path, storage_root))
        monkeypatch.setattr("interfaces_impl.access.mysql.MysqlAccessRecordEntry.create_instance", lambda config: nullcontext(MysqlAccessRecordEntry(db_session)))
        assert attach_chunk_main() == 0

    second_parent = _create_parent_document(
        db_session,
        storage_root,
        "second_parent.txt",
        "klmnopqrst",
    )
    first_chunk = next((record for record in MysqlAccessRecordEntry(db_session).get_all_records() if record.parent_id == parent.id and record.id != parent.id))
    capsys.readouterr()
    monkeypatch.setattr("sys.argv", [
        "delete_doc.py",
        "-ids",
        f"{parent.id},{first_chunk.id},{second_parent.id},{parent.id}",
    ])
    monkeypatch.setattr("backend.dispatcher.runtime.load_runtime_config", lambda config=None: _mysql_backend_config(tmp_path, storage_root))
    monkeypatch.setattr("interfaces_impl.access.mysql.MysqlAccessRecordEntry.create_instance", lambda config: nullcontext(MysqlAccessRecordEntry(db_session)))

    assert delete_doc_main() == 0
    result = json.loads(capsys.readouterr().out)

    assert result == {
        "deleted from DB": 4,
        "deleted from storage": 4,
        "not_found": [],
        "error_code": 0,
    }
    assert MysqlAccessRecordEntry(db_session).get_all_records() == []
    assert PersistentStorageRecordEntry(storage_root).get_all_records() == {}


def test_delete_doc_deletes_valid_ids_and_reports_missing_ids(
    monkeypatch,
    tmp_path,
    db_session,
    db_engine,
    capsys,
):
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    parent = _create_parent_document(db_session, storage_root, "parent.txt", "abcdefghij")

    monkeypatch.setattr(
        "sys.argv",
        ["delete_doc.py", "-ids", f"{parent.id},999"],
    )
    monkeypatch.setattr(
        "backend.dispatcher.runtime.load_runtime_config",
        lambda config=None: _mysql_backend_config(tmp_path, storage_root),
    )
    monkeypatch.setattr(
        "interfaces_impl.access.mysql.MysqlAccessRecordEntry.create_instance",
        lambda config: nullcontext(MysqlAccessRecordEntry(db_session)),
    )

    assert delete_doc_main() == 0
    result = json.loads(capsys.readouterr().out)

    assert result["deleted from DB"] == 1
    assert result["deleted from storage"] == 1
    assert result["error_code"] == 0
    assert result["not_found"] == [999]
    assert "error_msg" not in result
    assert MysqlAccessRecordEntry(db_session).get_all_records() == []
    assert PersistentStorageRecordEntry(storage_root).get_all_records() == {}


@pytest.mark.parametrize("failure_stage", ["metadata", "database"])
def test_uri_insertion_failure_preserves_source(monkeypatch, tmp_path, db_session, failure_stage):
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    source = tmp_path / "source.txt"
    original = " \nисходный документ\t\n".encode("utf-8")
    source.write_bytes(original)
    access = MysqlAccessRecordEntry(db_session)
    store = PersistentStorageRecordEntry(storage_root)
    backend = MysqlPersistentBackend(access=access, store=store)

    def fail(*args, **kwargs):
        raise RuntimeError("simulated insertion failure")

    if failure_stage == "metadata":
        monkeypatch.setattr(PersistentStorageRecordEntry, "write_fields", fail)
    else:
        monkeypatch.setattr(access, "update_record_by_id", fail)

    with pytest.raises(RuntimeError, match="simulated insertion failure"):
        backend.put_doc_by_uri(source)

    assert source.read_bytes() == original
    assert list(storage_root.iterdir()) == []
    assert access.get_all_records() == []
