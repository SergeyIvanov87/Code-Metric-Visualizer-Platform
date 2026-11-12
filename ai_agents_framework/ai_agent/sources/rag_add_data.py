#!/usr/bin/env python

import argparse
import base64
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from document_splitter import split_document
from rag_chroma import insert_embeddings
from rag_chunks import attach_chunks
from fs_api_wrappers import (
    create_api_query_interruptible, get_normalized_api_queries,
    generate_inner_session_id,
    execute_delete_doc_query,
    execute_put_doc_data_query,
)

def main(
    shared_api_dir: str,
    main_service_name: str,
    sess_id: str,
    db_host: str,
    db_port: int,
    doc_data: str,
    doc_metadata: str,
    doc_type: str,
    timeout: int,
    filename: str = None,
):
    filename = filename or (
        datetime.now(timezone.utc).strftime("%Y-%m-%d:%H:%M:%S_") + doc_type
    )

    from embedding_model import get_embedding_model

    # Break down a doc onto chunks
    embedding_model = get_embedding_model()

    doc_chunks = split_document(
        doc_data, doc_type, max_chunk_size=220, max_chunk_overlap_count=30
    )
    if len(doc_chunks) == 0:
        raise RuntimeError(
            f"The document: data cannot be split onto chunks, session: {sess_id}"
        )

    chunk_texts = [chunk.page_content for chunk in doc_chunks]
    chunk_embeddings = embedding_model.embed_documents(chunk_texts)

    # Create API handles
    doc_encoding_type = "base64"
    doc_type_for_dispatcher = doc_encoding_type + "," + doc_type
    normalized_api_queries = get_normalized_api_queries(
        shared_api_dir,
        main_service_name,
        {
            "put_doc_data": re.compile(r".*[/_]ai_agent_rag_dispatcher[/_]put_doc_data[/_]v[0-9]+(?:[/_]PUT)?/?$"),
            "attach_doc_chunk": re.compile(
                ".*ai_agent_rag_dispatcher.*attach_doc_chunk.*"
            ),
            "delete_doc": re.compile(r".*ai_agent_rag_dispatcher.*delete_doc.*"),
        },
    )
    session_id = generate_inner_session_id(sess_id)
    put_doc_query = create_api_query_interruptible(
        shared_api_dir, normalized_api_queries["put_doc_data"], session_id
    )
    attach_doc_chunk_query = create_api_query_interruptible(
        shared_api_dir, normalized_api_queries["attach_doc_chunk"], session_id
    )
    delete_doc_query = create_api_query_interruptible(
        shared_api_dir, normalized_api_queries["delete_doc"], session_id
    )

    # insert the main doc
    timeout_elapsed = timeout
    doc_data_bytes = doc_data.encode("utf-8")
    encoded_doc_data = base64.b64encode(doc_data_bytes).decode("ascii")
    put_doc_result = execute_put_doc_data_query(
        put_doc_query,
        session_id,
        timeout_elapsed,
        encoded_doc_data,
        doc_type_for_dispatcher,
        doc_metadata,
        filename=filename,
    )
    doc_unique_id = put_doc_result["unique_id"]

    # push chunks into doc storage
    chunk_unique_ids = []
    chunk_metadata = []

    try:
        chunk_unique_ids, chunk_metadata = attach_chunks(
            attach_doc_chunk_query, session_id, doc_unique_id,
            doc_type_for_dispatcher, doc_metadata, chunk_texts,
        )

        # eventually push doc & chunks into chroma
        my_collection_name = main_service_name
        try:

            insert_embeddings(
                db_host, db_port, my_collection_name,
                chunk_unique_ids, chunk_embeddings, chunk_metadata,
            )
        except Exception as ex:
            raise RuntimeError(
                f"Cannot insert embeddings: {len(chunk_embeddings)} into ChromaDB: {db_host}:{db_port} for collectiond: {my_collection_name}, session: {session_id}, exception: {ex}"
            ) from ex
    except RuntimeError as ex:
        timeout_elapsed = 10
        try:
            delete_doc_result = execute_delete_doc_query(
                delete_doc_query,
                session_id,
                timeout_elapsed,
                doc_unique_id,
                doc_metadata,
            )
        except RuntimeError as delete_ex:
            raise RuntimeError(
                f"Cannot rollback state be deleting the main document by id: {doc_unique_id}, session: {session_id}\nInitial exception: {delete_ex}.\nRecords can be inconsistent"
            ) from delete_ex
        raise RuntimeError(
            f"The error had happened:\n{ex}\nRollback was finished. Records are consistent"
        ) from ex
    return doc_unique_id, chunk_unique_ids


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="Add a document to RAG")
    parser.add_argument(
        "-db_host",
        "--db_host",
        type=str,
        help="hostname of address of a Vector DB service",
    )
    parser.add_argument(
        "-db_port",
        "--db_port",
        type=int,
        help="the listening port of a Vector DB service",
    )
    parser.add_argument(
        "shared_api_dir", type=Path, help="Root path of the mounted API dir"
    )
    parser.add_argument("main_service_name", type=str, help="the main service name")
    parser.add_argument(
        "-session_id", "--session_id", type=str, help="Session identifier"
    )
    parser.add_argument("-metadata", "--metadata", type=str, default=None, help="document metadata")
    parser.add_argument("-doc_type", "--doc_type", type=str, required=True, help="document type")
    parser.add_argument("-timeout", "--timeout", type=int, default=20, help="dispatcher timeout in seconds")
    parser.add_argument("-filename", "--filename", default=None, help="Optional stored document filename")

    args = parser.parse_args()
    doc_type = args.doc_type
    error_code = 0
    return_data = {"error_code": error_code, "error_msg": "success", "doc_id": "", "chunk_ids": []}
    try:
        document_data_bytes = sys.stdin.read().encode("utf-8")
        document_data = base64.b64decode(document_data_bytes).decode("utf-8")
        doc_id, chunk_ids = main(
            args.shared_api_dir,
            args.main_service_name,
            args.session_id,
            args.db_host,
            args.db_port,
            document_data,
            args.metadata,
            doc_type,
            args.timeout,
            filename=args.filename,
        )
        return_data["doc_id"] = doc_id
        return_data["chunk_ids"] = chunk_ids
    except Exception as ex:
        error_code = -1
        return_data["error_code"] = error_code
        return_data["error_msg"] = f"Couldn't add doc from document data, doc_type: {doc_type} into RAG, error: {ex}"

    print(json.dumps(return_data))
    sys.exit(error_code)
