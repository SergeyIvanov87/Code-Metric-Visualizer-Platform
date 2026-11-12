#!/usr/bin/env python

import argparse
import base64
import json
import re
import sys


from pathlib import Path

from fs_api_wrappers import (
    create_api_query_interruptible,
    get_normalized_api_queries,
    generate_inner_session_id,
    execute_attach_doc_chunks_query,
    execute_delete_doc_query,
)

def split_document(doc_data, doc_type, max_chunk_size, max_chunk_overlap_count):
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    chunks = []
    if "txt" in doc_type:
        splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="cl100k_base",
            chunk_size=max_chunk_size,  # tokens
            chunk_overlap=max_chunk_overlap_count,  # around 15%
            separators=[
                "\n\n",  # paragraphs
                "\n",  # lines
                ". ",  # sentences
                " ",  # words
                "",
            ],
        )
        chunks = splitter.create_documents(
            texts=[doc_data],
            metadatas=[],
        )
        # TODO move creation of hugging face embeddings here
        #
    return chunks


def ingest_document(
    shared_api_dir: str,
    main_service_name: str,
    sess_id: str,
    db_host: str,
    db_port: int,
    doc_uri: str,
    doc_metadata: str,
    doc_type: str,
    doc_data: str,
    timeout: int,
    put_query_name,
    insert_document,
):
    import chromadb
    from langchain_chroma import Chroma

    from embedding_model import get_embedding_model

    # Break down a doc onto chunks
    embedding_model = get_embedding_model()

    doc_chunks = split_document(
        doc_data, doc_type, max_chunk_size=220, max_chunk_overlap_count=30
    )
    if len(doc_chunks) == 0:
        raise RuntimeError(
            f"The document: {doc_uri} cannot be split onto chunks, session: {sess_id}"
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
            put_query_name: re.compile(r".*ai_agent_rag_dispatcher.*" + put_query_name + r"_v[0-9]+$"),
            "attach_doc_chunk": re.compile(
                ".*ai_agent_rag_dispatcher.*attach_doc_chunk.*"
            ),
            "delete_doc": re.compile(r".*ai_agent_rag_dispatcher.*delete_doc.*"),
        },
    )
    session_id = generate_inner_session_id(sess_id)
    put_doc_query = create_api_query_interruptible(
        shared_api_dir, normalized_api_queries[put_query_name], session_id
    )
    attach_doc_chunk_query = create_api_query_interruptible(
        shared_api_dir, normalized_api_queries["attach_doc_chunk"], session_id
    )
    delete_doc_query = create_api_query_interruptible(
        shared_api_dir, normalized_api_queries["delete_doc"], session_id
    )

    put_doc_result = insert_document(
        put_doc_query, session_id, timeout, doc_type_for_dispatcher,
    )
    doc_unique_id = put_doc_result["unique_id"]

    # push chunks into doc storage
    chunk_unique_ids = []
    chunk_metadata = []

    try:
        try:
            chunk_bytes = [base64.b64encode(c.encode('utf-8')).decode('utf-8') for c in chunk_texts]

            timeout_elapsed = 10 * len(chunk_bytes)
            chunk_unique_ids, chunk_metadata = execute_attach_doc_chunks_query(
                attach_doc_chunk_query,
                session_id,
                timeout_elapsed,
                doc_unique_id,
                doc_type_for_dispatcher,
                doc_metadata,
                chunk_bytes,
            )
        except Exception as ex:
            raise RuntimeError(
                f"Cannot attach chunks: {len(chunk_texts)} to the doc id: {doc_unique_id}, session: {session_id}, exception: {ex}"
            ) from ex

        # eventually push doc & chunks into chroma
        my_collection_name = main_service_name
        try:

            chromadb_client = chromadb.HttpClient(host=db_host, port=db_port)
            vectordb_client = Chroma(client=chromadb_client)  # not realy needed.

            collection = chromadb_client.get_or_create_collection(
                name=my_collection_name
            )
            collection.add(
                ids=chunk_unique_ids,
                embeddings=chunk_embeddings,
                metadatas=chunk_metadata,
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

def run_cli(handler, inline=False):
    """Parse shared connection options and report a structured ingestion result."""
    parser = argparse.ArgumentParser(prog="Add document data to RAG" if inline else "Add a document URI to RAG")
    parser.add_argument("shared_api_dir", type=Path)
    parser.add_argument("main_service_name")
    parser.add_argument("--db_host", "-db_host")
    parser.add_argument("--db_port", "-db_port", type=int)
    parser.add_argument("--session_id", "-session_id")
    parser.add_argument("--metadata", "-metadata", default=None)
    parser.add_argument("--doc_type", "-doc_type", default=None)
    parser.add_argument("--timeout", "-timeout", type=int, default=20)
    if not inline:
        parser.add_argument("--URI", "-URI", dest="uri")
        parser.add_argument("--preserveOriginal", type=int, choices=(0, 1), default=1)
    args = parser.parse_args()
    result = {"error_code": 0, "error_msg": "success", "doc_id": "", "chunk_ids": []}
    try:
        if inline:
            if not args.doc_type:
                raise ValueError("doc_type is required for inline document data")
            data = base64.b64decode(sys.stdin.buffer.read()).decode("utf-8")
            ids = handler(args.shared_api_dir, args.main_service_name, args.session_id,
                          args.db_host, args.db_port, data, args.metadata, args.doc_type, args.timeout)
        else:
            ids = handler(args.shared_api_dir, args.main_service_name, args.session_id,
                          args.db_host, args.db_port, args.uri, args.metadata, args.doc_type,
                          args.timeout, preserveOriginal=args.preserveOriginal)
        result["doc_id"], result["chunk_ids"] = ids
    except Exception as error:
        result.update(error_code=-1, error_msg=f"Couldn't add document into RAG: {error}")
    print(json.dumps(result))
    return result["error_code"]


def validate_document_type(doc_type):
    if doc_type.split(",", 1)[0] == "image":
        raise ValueError('The "image" document category is unsupported')
