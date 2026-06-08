#!/usr/bin/python

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from api_fs_query import APIQuery
from api_schema_utils import compose_api_queries_pipe_names
from settings import Settings
from utils import get_api_queries


API_ROOT = Path("/API")
DATA_ROOT = Path("/package/test_data")
STORAGE_ROOT = Path(os.getenv("PERSISTENT_STORAGE_DIR", "/mnt")) / "file_storage"

global_settings = Settings()
API_QUERIES = get_api_queries(str(API_ROOT), global_settings.domain_name_api_entry)


def _query(name: str) -> dict:
    assert name in API_QUERIES, f"API schema '{name}' must be present in {API_ROOT}"
    return API_QUERIES[name]


def _api_query(name: str) -> APIQuery:
    return APIQuery(compose_api_queries_pipe_names(global_settings.api_dir, _query(name)))


def _session_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _execute_json_api(name: str, args: dict[str, object] | None = None) -> dict:
    args = args or {}
    session_id = str(args.pop("SESSION_ID", _session_id(name)))
    exec_args = " ".join([f"SESSION_ID={session_id}", *[f"{key}={value}" for key, value in args.items()]])

    query = _api_query(name)
    assert query.wait_until_valid(0.1, 100, True), f"API query '{name}' did not become ready"
    query.execute(exec_args)
    raw_result = query.wait_result(session_id, 0.1, 300, True)
    try:
        return json.loads(raw_result)
    except json.JSONDecodeError as exc:
        pytest.fail(f"API query '{name}' returned non-JSON result: {raw_result!r}. Error: {exc}")


def _data_text(name: str) -> str:
    return (DATA_ROOT / name).read_text(encoding="utf-8")


def _api_safe_payload(text: str) -> str:
    # Generated FS API scripts split request data by shell words, so fixture data used
    # through the API must avoid spaces while preserving enough content to validate flow.
    return text.strip().replace(" ", "_")


def _record_dir(record_id: int) -> Path:
    return STORAGE_ROOT / str(record_id)


def _storage_file(record_dir: Path) -> Path:
    files = list(record_dir.glob("*.storage_bin"))
    assert len(files) == 1, f"Expected one storage payload file in {record_dir}, got {files}"
    return files[0]


def _read_int(path: Path) -> int:
    return int(path.read_text(encoding="utf-8").strip())


def _storage_record_ids() -> set[int]:
    if not STORAGE_ROOT.exists():
        return set()
    return {int(entry.name) for entry in STORAGE_ROOT.iterdir() if entry.is_dir() and entry.name.isdigit()}


def _assert_document_storage(record_id: int, file_uri: str, document_data: str) -> None:
    record_dir = _record_dir(record_id)
    assert record_dir.is_dir()

    payload_file = _storage_file(record_dir)
    assert payload_file.stem == Path(file_uri).name
    assert payload_file.read_text(encoding="utf-8") == document_data
    assert _read_int(record_dir / "parentId") == record_id
    assert _read_int(record_dir / "offset") == 0
    assert _read_int(record_dir / "size") == len(document_data.encode("utf-8"))


def _assert_chunk_storage(
    record_id: int,
    parent_id: int,
    parent_file_uri: str,
    parent_data: str,
    chunk_data: str,
    metadata: str,
) -> None:
    record_dir = _record_dir(record_id)
    assert record_dir.is_dir()

    payload_file = _storage_file(record_dir)
    assert payload_file.stem == Path(parent_file_uri).name
    assert payload_file.read_bytes() == b""

    expected_offset = parent_data.find(chunk_data)
    assert expected_offset >= 0

    assert _read_int(record_dir / "parentId") == parent_id
    assert _read_int(record_dir / "offset") == expected_offset
    assert _read_int(record_dir / "size") == len(chunk_data.encode("utf-8"))
    assert (record_dir / "metadata").read_text(encoding="utf-8") == metadata


def _assert_storage_absent(*record_ids: int) -> None:
    for record_id in record_ids:
        assert not _record_dir(record_id).exists()


def _sync() -> dict:
    return _execute_json_api("sync")


def _sync_counter(payload: dict, *names: str) -> int:
    for name in names:
        if name in payload:
            return int(payload[name])
    raise AssertionError(f"Sync response is missing counters {names}: {payload}")


def _assert_sync_is_clean(expected_storage_records: int | None = None, expected_to_delete: int = 0) -> dict:
    payload = _sync()

    assert _sync_counter(payload["output"], "created", "not_changed") == 0
    assert _sync_counter(payload["output"], "updated") == 0
    assert _sync_counter(payload["output"], "deleted") == expected_to_delete

    storage_size = _sync_counter(payload["output"], "storage size")
    initial_db_records = _sync_counter(payload["output"], "initial DB records")
    assert initial_db_records == storage_size
    if expected_storage_records is not None:
        assert storage_size == expected_storage_records
    return payload


def _put_doc(file_uri: str, document_data: str, metadata: str = "test_metadata") -> int:
    payload = _execute_json_api(
        "put_doc",
        {
            "-URI": file_uri,
            "-metadata": metadata,
            "data": document_data,
        },
    )
    assert payload["error_code"] == 0, payload
    assert "unique_id" in payload
    return int(payload["unique_id"])


def _attach_chunk(doc_id: int, chunk_data: str, metadata: str) -> int:
    payload = _execute_json_api(
        "attach_doc_chunk",
        {
            "-doc_id": doc_id,
            "-metadata": metadata,
            "data": chunk_data,
        },
    )
    assert payload["error_code"] == 0, payload
    assert "unique_id" in payload
    return int(payload["unique_id"])


def _delete_doc(record_id: int) -> dict:
    payload = _execute_json_api(
        "delete_doc",
        {
            "-id": record_id,
            "-metadata": "functional_delete",
        },
    )
    assert payload["error_code"] == 0, payload
    return payload


def _create_storage_document(record_id: int, file_uri: str, content: str) -> None:
    record_dir = _record_dir(record_id)
    record_dir.mkdir(mode=0o777,parents=True, exist_ok=False)
    (record_dir / f"{Path(file_uri).name}.storage_bin").write_text(content, encoding="utf-8")
    (record_dir / "parentId").write_text(str(record_id), encoding="utf-8")
    (record_dir / "offset").write_text("0", encoding="utf-8")
    (record_dir / "size").write_text(str(len(content.encode("utf-8"))), encoding="utf-8")


def _create_storage_chunk(record_id: int, parent_id: int, parent_file_uri: str, parent_data: str, chunk_data: str) -> None:
    record_dir = _record_dir(record_id)
    record_dir.mkdir(mode=0o777, parents=True, exist_ok=False)
    (record_dir / f"{Path(parent_file_uri).name}.storage_bin").touch()
    (record_dir / "parentId").write_text(str(parent_id), encoding="utf-8")
    (record_dir / "offset").write_text(str(parent_data.find(chunk_data)), encoding="utf-8")
    (record_dir / "size").write_text(str(len(chunk_data.encode("utf-8"))), encoding="utf-8")
    (record_dir / "metadata").write_text("", encoding="utf-8")


@pytest.fixture()
def created_record_ids():
    os.umask(0)
    _assert_sync_is_clean()
    record_ids: list[int] = []
    yield record_ids

    for record_id in sorted(set(record_ids), reverse=True):
        if _record_dir(record_id).exists():
            try:
                _delete_doc(record_id)
            except Exception:
                shutil.rmtree(_record_dir(record_id), ignore_errors=True)
    _assert_sync_is_clean()


def test_put_documents_create_matching_storage_records(created_record_ids):
    doc_0 = _api_safe_payload(_data_text("doc_0.txt"))
    doc_1 = _api_safe_payload(_data_text("doc_1.txt"))

    before_ids = _storage_record_ids()
    doc_0_id = _put_doc("doc_0.txt", doc_0)
    created_record_ids.append(doc_0_id)
    _assert_document_storage(doc_0_id, "doc_0.txt", doc_0)
    _assert_sync_is_clean(len(before_ids) + 1)

    doc_1_id = _put_doc("doc_1.txt", doc_1)
    created_record_ids.append(doc_1_id)
    _assert_document_storage(doc_1_id, "doc_1.txt", doc_1)
    _assert_sync_is_clean(len(before_ids) + 2)


def test_put_documents_with_chunks_create_matching_storage_records(created_record_ids):
    doc_0 = _api_safe_payload(_data_text("doc_0.txt"))
    doc_1 = _api_safe_payload(_data_text("doc_1.txt"))
    doc_0_chunk_0 = _api_safe_payload(_data_text("doc_0_chunk_0.txt"))
    doc_0_chunk_1 = _api_safe_payload(_data_text("doc_0_chunk_1.txt"))
    doc_1_chunk_0 = _api_safe_payload(_data_text("doc_1_chunk_0.txt"))
    doc_1_chunk_1 = _api_safe_payload(_data_text("doc_1_chunk_1.txt"))

    before_ids = _storage_record_ids()
    doc_0_id = _put_doc("doc_0.txt", doc_0)
    doc_1_id = _put_doc("doc_1.txt", doc_1)
    created_record_ids.extend([doc_0_id, doc_1_id])

    chunk_specs = [
        (doc_0_id, "doc_0.txt", doc_0, doc_0_chunk_0, "chunk_0_for_doc_0"),
        (doc_0_id, "doc_0.txt", doc_0, doc_0_chunk_1, "chunk_1_for_doc_0"),
        (doc_1_id, "doc_1.txt", doc_1, doc_1_chunk_0, "chunk_0_for_doc_1"),
        (doc_1_id, "doc_1.txt", doc_1, doc_1_chunk_1, "chunk_1_for_doc_1"),
    ]

    for parent_id, parent_file_uri, parent_data, chunk_data, metadata in chunk_specs:
        chunk_id = _attach_chunk(parent_id, chunk_data, metadata)
        created_record_ids.append(chunk_id)
        _assert_chunk_storage(chunk_id, parent_id, parent_file_uri, parent_data, chunk_data, metadata)

    _assert_sync_is_clean(len(before_ids) + 6)


def test_docs_deletion_removes_storage_records(created_record_ids):
    doc_0 = _api_safe_payload(_data_text("doc_0.txt"))
    doc_1 = _api_safe_payload(_data_text("doc_1.txt"))

    before_ids = _storage_record_ids()
    doc_0_id = _put_doc("doc_0.txt", doc_0)
    doc_1_id = _put_doc("doc_1.txt", doc_1)
    created_record_ids.extend([doc_0_id, doc_1_id])

    delete_result = _delete_doc(doc_0_id)
    created_record_ids.remove(doc_0_id)

    assert delete_result["deleted from storage"] == 1
    _assert_storage_absent(doc_0_id)
    _assert_document_storage(doc_1_id, "doc_1.txt", doc_1)
    _assert_sync_is_clean(len(before_ids) + 1)


def test_docs_and_chunks_deletion_removes_whole_storage_tree(created_record_ids):
    doc_0 = _api_safe_payload(_data_text("doc_0.txt"))
    doc_0_chunk_0 = _api_safe_payload(_data_text("doc_0_chunk_0.txt"))
    doc_0_chunk_1 = _api_safe_payload(_data_text("doc_0_chunk_1.txt"))

    before_ids = _storage_record_ids()
    doc_0_id = _put_doc("doc_0.txt", doc_0)
    chunk_0_id = _attach_chunk(doc_0_id, doc_0_chunk_0, "chunk_0_for_doc_0")
    chunk_1_id = _attach_chunk(doc_0_id, doc_0_chunk_1, "chunk_1_for_doc_0")
    created_record_ids.extend([doc_0_id, chunk_0_id, chunk_1_id])

    delete_result = _delete_doc(doc_0_id)
    created_record_ids.clear()

    assert delete_result["deleted from storage"] == 3
    _assert_storage_absent(doc_0_id, chunk_0_id, chunk_1_id)
    _assert_sync_is_clean(len(before_ids))


def test_sync_recreates_db_records_added_to_storage(created_record_ids):

    before_ids = _storage_record_ids()
    base_id = int(time.time() * 1000)
    while _record_dir(base_id).exists() or _record_dir(base_id + 1).exists():
        base_id += 2

    doc_id = base_id
    chunk_id = base_id + 1
    document_data = "manual_document_inserted_into_file_storage"
    chunk_data = "manual_document"

    _create_storage_document(doc_id, "manual_doc.txt", document_data)
    _create_storage_chunk(chunk_id, doc_id, "manual_doc.txt", document_data, chunk_data)
    created_record_ids.extend([doc_id, chunk_id])

    sync_result = _sync()
    assert _sync_counter(sync_result["output"], "created") == 2
    _assert_document_storage(doc_id, "manual_doc.txt", document_data)
    _assert_chunk_storage(chunk_id, doc_id, "manual_doc.txt", document_data, chunk_data, "")
    _assert_sync_is_clean(len(before_ids) + 2)
