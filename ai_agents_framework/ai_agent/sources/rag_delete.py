#!/usr/bin/env python

import argparse
import json
import re
import sys
from pathlib import Path

import chromadb

from fs_api_wrappers import (
    create_api_query_interruptible,
    execute_delete_doc_query,
    generate_inner_session_id,
    get_normalized_api_queries,
)


def parse_ids(value: str) -> list[int]:
    """Parse a comma-separated document ID list without changing its order."""
    values = value.split(",")
    if not value or any(not item.strip() for item in values):
        raise argparse.ArgumentTypeError("IDs must be comma-separated integers")
    try:
        ids = [int(item.strip()) for item in values]
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "IDs must be comma-separated integers"
        ) from error
    return list(dict.fromkeys(ids))


def main(
    shared_api_dir: Path,
    main_service_name: str,
    sess_id: str,
    db_host: str,
    db_port: int,
    doc_ids: list[int],
    doc_metadata: str | None,
) -> dict:
    """Delete documents from the dispatcher and their vectors from Chroma."""
    normalized_api_queries = get_normalized_api_queries(
        shared_api_dir,
        main_service_name,
        {
            "delete_doc": re.compile(
                r".*ai_agent_rag_dispatcher.*delete_doc.*"
            ),
        },
    )
    session_id = generate_inner_session_id(sess_id, "rag_delete")
    delete_query = create_api_query_interruptible(
        shared_api_dir, normalized_api_queries["delete_doc"], session_id
    )

    chroma_client = chromadb.HttpClient(host=db_host, port=db_port)
    collection = None
    chunk_ids: list[str] = []
    try:
        collection = chroma_client.get_collection(name=main_service_name)
    except chromadb.errors.NotFoundError:
        pass
    if collection is not None:
        records = collection.get(where={"doc_id": {"$in": doc_ids}})
        chunk_ids = list(dict.fromkeys(records.get("ids", [])))

    dispatcher_result = execute_delete_doc_query(
        delete_query,
        session_id,
        timeout_elapsed=10,
        doc_id=",".join(str(doc_id) for doc_id in doc_ids),
        doc_metadata=doc_metadata,
    )
    if collection is not None and chunk_ids:
        collection.delete(ids=chunk_ids)

    return {
        "error_code": 0,
        "error_msg": "success",
        "document_ids": doc_ids,
        "deleted_chunk_ids": chunk_ids,
        "dispatcher": dispatcher_result,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="Delete documents from RAG")
    parser.add_argument("-db_host", "--db_host", required=True)
    parser.add_argument("-db_port", "--db_port", required=True, type=int)
    parser.add_argument("shared_api_dir", type=Path)
    parser.add_argument("main_service_name")
    parser.add_argument("-session_id", "--session_id", required=True)
    parser.add_argument("-ids", "--ids", required=True, type=parse_ids)
    parser.add_argument("-metadata", "--metadata")
    args = parser.parse_args()

    exit_code = 0
    try:
        result = main(
            args.shared_api_dir,
            args.main_service_name,
            args.session_id,
            args.db_host,
            args.db_port,
            args.ids,
            args.metadata,
        )
    except Exception as error:
        exit_code = 1
        result = {
            "error_code": exit_code,
            "error_msg": f"Couldn't delete RAG documents, error: {error}",
        }
    print(json.dumps(result))
    sys.exit(exit_code)
