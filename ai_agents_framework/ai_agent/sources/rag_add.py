#!/usr/bin/env python

import argparse
import json
import re
import sys


from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from fs_api_wrappers import (
    create_api_query_interruptible,
    get_normalized_api_queries,
    generate_inner_session_id,
    execute_put_doc_query,
    execute_attach_doc_chunks_query,
)


def split_document(doc_data, doc_metadata, max_chunk_size, max_chunk_overlap_count):
    chunks = []
    if len(doc_metadata) == 0 or doc_metadata.lower().find("txt") != -1:
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


def main(
    shared_api_dir: str,
    main_service_name: str,
    sess_id: str,
    db_host: str,
    db_port: int,
    doc_uri: str,
    doc_metadata: str,
    doc_data: str,
):
    normalized_api_queries = get_normalized_api_queries(
        shared_api_dir,
        main_service_name,
        {
            "put_doc": re.compile(r".*ai_agent_rag_dispatcher.*put_doc.*"),
            "attach_doc_chunk": re.compile(
                ".*ai_agent_rag_dispatcher.*attach_doc_chunk.*"
            ),
        },
    )

    # Create API handles
    session_id = generate_inner_session_id(sess_id)
    put_doc_query = create_api_query_interruptible(
        shared_api_dir, normalized_api_queries["put_doc"], session_id
    )
    attach_doc_chunk_query = create_api_query_interruptible(
        shared_api_dir, normalized_api_queries["attach_doc_chunk"], session_id
    )

    # insert doc
    timeout_elapsed = 10
    put_doc_result = execute_put_doc_query(
        put_doc_query, session_id, timeout_elapsed, doc_uri, doc_data, doc_metadata
    )
    doc_unique_id = put_doc_result["unique_id"]

    # push chunks into doc storage
    # the main limitation is important: text beyond 256 word pieces is truncated. It is intended for sentences and short
    model_name = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_model = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={
            "device": "cpu",
        },
        encode_kwargs={
            "normalize_embeddings": True,
            "batch_size": 16,
        },
    )

    doc_chunks = split_document(
        doc_data, doc_metadata, max_chunk_size=220, max_chunk_overlap_count=30
    )
    if len(doc_chunks) == 0:
        raise RuntimeError("TODO! rollback main document insertion!!!")

    chunk_texts = [chunk.page_content for chunk in doc_chunks]
    chunk_embeddings = embedding_model.embed_documents(chunk_texts)

    # insert the chunks of the doc
    timeout_elapsed = 10
    chunk_unique_ids, chunk_metadata = execute_attach_doc_chunks_query(
        attach_doc_chunk_query, session_id, timeout_elapsed, doc_unique_id, chunk_texts
    )

    print(f"chunk_unique_ids: {chunk_unique_ids}, chunk_metadata: {chunk_metadata}")
    # eventually push doc & chunks into chroma
    chromadb_client = chromadb.HttpClient(host=db_host, port=db_port)
    vectordb_client = Chroma(client=chromadb_client)  # not realy needed.
    my_collection_name = main_service_name

    collection = chromadb_client.get_or_create_collection(name=my_collection_name)
    collection.add(
        ids=chunk_unique_ids, embeddings=chunk_embeddings, metadatas=chunk_metadata
    )
    """
    use this to retrive
    ~$ chroma browse api.pmccabe_collector.restapi.org --host http://rag-db:8000

    the complete list of REST API can be obtained by
    ~$ curl -sS http://rag-db:8000/openapi.json | jq -r '.paths | keys[]'


    OR
    ~$ curl -sS   http://rag-db:8000/api/v2/tenants/default_tenant/databases/default_database/collections
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=5,
        include=["distances"],
    )

    OR

    curl -sS   -X POST   "http://rag-db:8000/api/v2/tenants/default_tenant/databases/default_database/collections/<YOUR-COLLECTION-ID>/get"   -H "Content-Type: application/json"   -d '{
    "limit": 100,
    "offset": 0,
    "include": ["embeddings"]
  }' | jq

  OR

    matches = list(zip(
        results["ids"][0],
        results["distances"][0],
    ))

    for chunk_id, distance in matches:
        print(chunk_id, distance)
    """


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
    parser.add_argument("-URI", "--uri", type=str, help="The URi of a document")
    parser.add_argument("-metadata", "--metadata", type=str, help="document metadata")

    doc_data = "111111111"
    args = parser.parse_args()
    error_code = 0
    # try:
    main(
        args.shared_api_dir,
        args.main_service_name,
        args.session_id,
        args.db_host,
        args.db_port,
        args.uri,
        args.metadata,
        doc_data,
    )
    # except Exception as ex:
    #    print(f"Execution of {__file__} failed, exception: {ex}", file=sys.stderr)
    #    error_code = -1

    sys.exit(error_code)
