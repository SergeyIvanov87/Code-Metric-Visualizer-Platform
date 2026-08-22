#!/usr/bin/env python

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_NOT_FOUND_RESPONSE = "<Not found ID>"
_DELETE_BATCH_SIZE = 1000


@dataclass
class ChromaSyncState:
    initial_chroma_ids: set[str] = field(default_factory=set)
    source_chunk_ids: set[str] = field(default_factory=set)
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)


@dataclass
class RagSyncProgress:
    chroma: ChromaSyncState = field(default_factory=ChromaSyncState)
    filesystem_db_sync: dict[str, Any] = field(default_factory=dict)

    def to_result(self) -> dict[str, Any]:
        result = chroma_sync_result(self.chroma)
        result["filesystem_db_sync"] = self.filesystem_db_sync
        return result


def extract_chunk_records(get_docs_result: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(get_docs_result, dict):
        raise RuntimeError("rag_get_docs returned a non-object response")
    if get_docs_result.get("error_code", 0) != 0:
        raise RuntimeError(
            f"rag_get_docs failed: {get_docs_result.get('error_msg', get_docs_result)}"
        )

    docs = get_docs_result.get("docs")
    if not isinstance(docs, list):
        raise RuntimeError("rag_get_docs response does not contain a docs array")

    records = []
    seen_chunk_ids = set()
    for document in docs:
        if not isinstance(document, dict) or "id" not in document:
            raise RuntimeError(f"rag_get_docs returned an invalid document: {document}")
        chunks = document.get("chunks")
        if not isinstance(chunks, list):
            raise RuntimeError(
                f"rag_get_docs document {document['id']} does not contain a chunks array"
            )

        for chunk_num, chunk_id in enumerate(chunks):
            chroma_id = str(chunk_id)
            if chroma_id in seen_chunk_ids:
                raise RuntimeError(
                    f"rag_get_docs returned duplicate chunk id: {chroma_id}"
                )
            seen_chunk_ids.add(chroma_id)
            records.append(
                {
                    "id": chroma_id,
                    "metadata": {
                        "doc_id": document["id"],
                        "chunk_num": chunk_num,
                        "chunk_id": chunk_id,
                    },
                }
            )
    return records


def _flatten_chroma_ids(raw_ids: Any) -> list[str]:
    if raw_ids is None:
        return []
    flattened = []
    for item in raw_ids:
        if isinstance(item, list):
            flattened.extend(str(nested_item) for nested_item in item)
        else:
            flattened.append(str(item))
    return flattened


def get_chroma_ids(collection) -> set[str]:
    result = collection.get(include=[])
    if not isinstance(result, dict):
        raise RuntimeError("Chroma returned an invalid response while listing IDs")
    return set(_flatten_chroma_ids(result.get("ids", [])))


def _delete_chroma_ids(
    collection, ids: list[str], state: ChromaSyncState
) -> None:
    for begin in range(0, len(ids), _DELETE_BATCH_SIZE):
        batch = ids[begin : begin + _DELETE_BATCH_SIZE]
        collection.delete(ids=batch)
        state.deleted.extend(batch)


def reconcile_chroma(
    collection,
    embedding_model,
    get_docs_result: dict[str, Any],
    read_chunk: Callable[[str], str],
    state: ChromaSyncState,
) -> ChromaSyncState:
    chunk_records = extract_chunk_records(get_docs_result)
    for record in chunk_records:
        chunk_id = record["id"]
        if chunk_id in state.source_chunk_ids:
            raise RuntimeError(
                f"rag_get_docs returned duplicate chunk id across pages: {chunk_id}"
            )
        state.source_chunk_ids.add(chunk_id)

        chunk_text = read_chunk(chunk_id)
        if chunk_text == _NOT_FOUND_RESPONSE:
            raise RuntimeError(
                f"read_id could not find chunk id {chunk_id} after dispatcher sync"
            )

        embedding = embedding_model.embed_documents([chunk_text])[0]
        collection.upsert(
            ids=[chunk_id],
            embeddings=[embedding],
            metadatas=[record["metadata"]],
        )
        if chunk_id in state.initial_chroma_ids:
            state.updated.append(chunk_id)
        else:
            state.created.append(chunk_id)
    return state


def chroma_sync_result(state: ChromaSyncState) -> dict[str, Any]:
    synchronized_count = len(state.created) + len(state.updated)
    current_chroma_size = (
        len(state.initial_chroma_ids) + len(state.created) - len(state.deleted)
    )
    return {
        "created": list(state.created),
        "updated": list(state.updated),
        "deleted": list(state.deleted),
        "not_changed": [],
        "synchronized_count": synchronized_count,
        "initial_chroma_records": len(state.initial_chroma_ids),
        "chroma_size": current_chroma_size,
    }


def finalize_chroma_reconciliation(
    collection,
    state: ChromaSyncState,
) -> dict[str, Any]:
    pending_deletions = sorted(
        state.initial_chroma_ids - state.source_chunk_ids - set(state.deleted)
    )
    _delete_chroma_ids(collection, pending_deletions, state)
    return chroma_sync_result(state)


def _validate_get_docs_page(
    get_docs_result: dict[str, Any],
    expected_offset: int,
) -> tuple[int, int]:
    if not isinstance(get_docs_result, dict):
        raise RuntimeError("rag_get_docs returned a non-object response")
    if get_docs_result.get("error_code", 0) != 0:
        raise RuntimeError(
            f"rag_get_docs failed: {get_docs_result.get('error_msg', get_docs_result)}"
        )

    try:
        response_offset = int(get_docs_result["offset"])
        returned_limit = int(get_docs_result["limit"])
        remaining = int(get_docs_result["remaining"])
    except (KeyError, TypeError, ValueError) as ex:
        raise RuntimeError(
            f"rag_get_docs returned invalid pagination data: {get_docs_result}"
        ) from ex

    docs = get_docs_result.get("docs")
    if not isinstance(docs, list):
        raise RuntimeError("rag_get_docs response does not contain a docs array")
    if response_offset != expected_offset:
        raise RuntimeError(
            f"rag_get_docs returned offset {response_offset}, expected {expected_offset}"
        )
    if returned_limit != len(docs):
        raise RuntimeError(
            "rag_get_docs limit does not match the number of returned documents"
        )
    if remaining < 0:
        raise RuntimeError("rag_get_docs returned a negative remaining value")
    if remaining > 0 and returned_limit == 0:
        raise RuntimeError(
            "rag_get_docs returned no documents while records still remain"
        )
    return returned_limit, remaining


def reconcile_chroma_pages(
    collection,
    embedding_model,
    batch_size: int,
    get_docs_page: Callable[[int, int], dict[str, Any]],
    read_chunk: Callable[[str], str],
    state: ChromaSyncState | None = None,
) -> dict[str, Any]:
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")

    if state is None:
        state = ChromaSyncState(initial_chroma_ids=get_chroma_ids(collection))
    offset = 0
    while True:
        get_docs_result = get_docs_page(offset, batch_size)
        returned_limit, remaining = _validate_get_docs_page(
            get_docs_result,
            expected_offset=offset,
        )
        reconcile_chroma(
            collection,
            embedding_model,
            get_docs_result,
            read_chunk,
            state,
        )
        if remaining == 0:
            break
        offset += returned_limit

    return finalize_chroma_reconciliation(collection, state)


def _validate_dispatcher_sync_result(sync_result: Any) -> dict[str, Any]:
    if not isinstance(sync_result, dict):
        raise RuntimeError("The rag_doc_dispatcher sync returned a non-object response")
    if sync_result.get("error_code") != 0:
        raise RuntimeError(
            "The rag_doc_dispatcher sync failed: "
            f"{sync_result.get('error_msg', sync_result)}"
        )
    output = sync_result.get("output")
    if not isinstance(output, dict):
        raise RuntimeError(
            "The rag_doc_dispatcher sync response does not contain an output object"
        )
    return output


def main(
    shared_api_dir: Path,
    main_service_name: str,
    sess_id: str,
    db_host: str,
    db_port: int,
    batch_size: int,
    progress: RagSyncProgress | None = None,
) -> dict[str, Any]:
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")
    if progress is None:
        progress = RagSyncProgress()

    import chromadb

    from embedding_model import get_embedding_model
    from fs_api_wrappers import (
        create_api_query_interruptible,
        execute_get_docs_query,
        execute_read_ids,
        execute_sync_query,
        generate_inner_session_id,
        get_normalized_api_queries,
    )

    normalized_api_queries = get_normalized_api_queries(
        shared_api_dir,
        main_service_name,
        {
            "sync": re.compile(r".*ai_agent_rag_dispatcher_sync.*"),
            "get_docs": re.compile(r".*ai_agent_rag_get_docs.*"),
            "read_id": re.compile(r".*ai_agent_rag_dispatcher_read_id.*"),
        },
    )

    sync_session_id = generate_inner_session_id(sess_id, "rag_sync_dispatcher")
    sync_query = create_api_query_interruptible(
        shared_api_dir, normalized_api_queries["sync"], sync_session_id
    )
    dispatcher_sync_result = execute_sync_query(
        sync_query, sync_session_id, timeout_elapsed=60
    )
    dispatcher_sync_output = _validate_dispatcher_sync_result(dispatcher_sync_result)
    progress.filesystem_db_sync = dispatcher_sync_output

    get_docs_session_id = generate_inner_session_id(sess_id, "rag_sync_get_docs")
    get_docs_query = create_api_query_interruptible(
        shared_api_dir, normalized_api_queries["get_docs"], get_docs_session_id
    )
    read_session_id = generate_inner_session_id(sess_id, "rag_sync_read_id")
    read_query = create_api_query_interruptible(
        shared_api_dir, normalized_api_queries["read_id"], read_session_id
    )

    def read_chunk(chunk_id: str) -> str:
        contents = execute_read_ids(
            read_query,
            read_session_id,
            timeout_elapsed=10,
            ids=[chunk_id],
        )
        return contents[chunk_id]

    chromadb_client = chromadb.HttpClient(host=db_host, port=db_port)
    collection = chromadb_client.get_or_create_collection(name=main_service_name)
    progress.chroma.initial_chroma_ids = get_chroma_ids(collection)

    def get_docs_page(offset: int, limit: int) -> dict[str, Any]:
        return execute_get_docs_query(
            get_docs_query,
            get_docs_session_id,
            timeout_elapsed=60,
            offset=offset,
            limit=limit,
        )

    reconcile_chroma_pages(
        collection,
        get_embedding_model(),
        batch_size,
        get_docs_page,
        read_chunk,
        state=progress.chroma,
    )
    return progress.to_result()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="Synchronize RAG storage")
    parser.add_argument(
        "-db_host",
        "--db_host",
        required=True,
        help="Hostname or address of the Vector DB service",
    )
    parser.add_argument(
        "-db_port",
        "--db_port",
        required=True,
        type=int,
        help="Listening port of the Vector DB service",
    )
    parser.add_argument(
        "-batch_size",
        "--batch_size",
        type=int,
        default=100,
        help="Number of documents to retrieve and reconcile per batch",
    )
    parser.add_argument(
        "shared_api_dir", type=Path, help="Root path of the mounted API directory"
    )
    parser.add_argument("main_service_name", help="Main API service name")
    parser.add_argument(
        "-session_id", "--session_id", required=True, help="Session identifier"
    )
    args = parser.parse_args()

    return_data = {"error_code": 0, "error_msg": "success", "output": {}}
    error_code = 0
    progress = RagSyncProgress()
    try:
        return_data["output"] = main(
            args.shared_api_dir,
            args.main_service_name,
            args.session_id,
            args.db_host,
            args.db_port,
            args.batch_size,
            progress,
        )
    except Exception as ex:
        error_code = -1
        return_data = {
            "error_code": error_code,
            "error_msg": f"Couldn't synchronize RAG storage, error: {ex}",
            "output": progress.to_result(),
        }

    print(json.dumps(return_data))
    sys.exit(error_code)
