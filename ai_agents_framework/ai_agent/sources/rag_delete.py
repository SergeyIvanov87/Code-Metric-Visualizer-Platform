#!/usr/bin/env python

import argparse
import json
import re
import sys
from pathlib import Path

from id_ranges import IdSelection, ids_expression, parse_id_ranges

import chromadb

from fs_api_wrappers import (
    create_api_query_interruptible,
    execute_delete_doc_query,
    generate_inner_session_id,
    get_normalized_api_queries,
)


def parse_ids(value: str) -> str:
    """Validate a compact selection without expanding its ranges."""
    parse_id_ranges(value)
    return value


def _document_filter(selection: str) -> dict:
    predicates = []
    for start, end in parse_id_ranges(selection):
        if start == end:
            predicates.append({"doc_id": {"$eq": start}})
        else:
            predicates.append({"$and": [
                {"doc_id": {"$gte": start}},
                {"doc_id": {"$lte": end}},
            ]})
    return predicates[0] if len(predicates) == 1 else {"$or": predicates}


def main(
    shared_api_dir: Path,
    main_service_name: str,
    sess_id: str,
    db_host: str,
    db_port: int,
    doc_ids: IdSelection,
    doc_metadata: str | None,
) -> dict:
    """Delete documents from the dispatcher and their vectors from Chroma."""
    if not isinstance(doc_ids, str):
        doc_ids = list(dict.fromkeys(doc_ids))
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
        where = (
            _document_filter(doc_ids) if isinstance(doc_ids, str)
            else {"doc_id": {"$in": list(doc_ids)}}
        )
        records = collection.get(where=where)
        chunk_ids = list(dict.fromkeys(records.get("ids", [])))

    dispatcher_result = execute_delete_doc_query(
        delete_query,
        session_id,
        timeout_elapsed=10,
        doc_id=ids_expression(doc_ids),
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
        "not_found": dispatcher_result.get("not_found", []),
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
