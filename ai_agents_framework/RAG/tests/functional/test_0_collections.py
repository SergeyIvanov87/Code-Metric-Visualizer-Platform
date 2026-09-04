#!/usr/bin/python

import numpy
import os
import pathlib
import pytest
import stat
import sys
import time

# Python
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


from pathlib import Path
from settings import Settings


class RAGSettings(Settings):
    def __init__(self):
        Settings.__init__(self)
        self.test_data = Path(self.work_dir) / "test_data"
        rag_uri = os.getenv("RAG_URI", "")
        self.rag_host, self.rag_port = rag_uri.split(":")

        self.sentence_transformer_ef = SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2", device="cpu", normalize_embeddings=False
        )


global_settings = RAGSettings()
testdata = [file for file in global_settings.test_data.iterdir()]


def test_collection():
    global global_settings
    client = chromadb.HttpClient(
        host=global_settings.rag_host, port=global_settings.rag_port
    )
    my_collection_name = "my_collection"

    collection = client.get_or_create_collection(name=my_collection_name)
    collections = client.list_collections()
    print(collections, file=sys.stdout, flush=True)
    collections_list = [c for c in collections if c.name == my_collection_name]
    assert len(collections_list)
    client.delete_collection(name=my_collection_name)

    new_collections = client.list_collections()
    collections_list = [c for c in new_collections if c.name == my_collection_name]
    assert len(collections_list) == 0


unique_ids = 0

test_documents_collections_count = 0


@pytest.mark.parametrize("docfile", testdata)
def test_documents_collections(docfile):
    # TODO skip PDF
    if docfile.suffix == ".pdf":
        return

    global global_settings
    client = chromadb.HttpClient(
        host=global_settings.rag_host, port=global_settings.rag_port
    )
    collection = client.get_or_create_collection(name="my_collection")

    global test_documents_collections_count
    docfile_content = ""
    with open(docfile) as f:
        docfile_content = f.read()

    single_doc_embeddings = global_settings.sentence_transformer_ef([docfile_content])
    collection.add(
        ids=[str(test_documents_collections_count)],
        documents=[docfile_content],
        embeddings=single_doc_embeddings,
    )
    test_documents_collections_count += 1

    assert collection.count() == test_documents_collections_count
    if test_documents_collections_count == len(testdata):
        client.delete_collection(name="my_collection")


def chunks(file_name):
    with open(file_name) as f:
        while content := f.readline():
            yield content


chunkded_doc_unique_id = 0


@pytest.fixture(scope="class")
def test_chunk_documents_aside_embeddings_teardown():
    yield None
    global global_settings
    client = chromadb.HttpClient(
        host=global_settings.rag_host, port=global_settings.rag_port
    )
    client.delete_collection(name="my_chunked_collection")


class TestChunks:
    @pytest.mark.parametrize("docfile", testdata)
    def test_chunk_documents_aside_embeddings(
        self, docfile, test_chunk_documents_aside_embeddings_teardown
    ):
        # TODO skip PDF
        if docfile.suffix == ".pdf":
            return

        global global_settings
        client = chromadb.HttpClient(
            host=global_settings.rag_host, port=global_settings.rag_port
        )
        collection = client.get_or_create_collection(name="my_chunked_collection")

        docfile_content = chunks(docfile)
        print(docfile_content, file=sys.stdout, flush=True)

        single_chunk_embed = []
        global chunkded_doc_unique_id
        global unique_ids
        chunkded_doc_unique_id += 1
        metadatas = []
        document_chunks_ids = []
        for chunk in docfile_content:
            single_chunk_embed.extend(global_settings.sentence_transformer_ef([chunk]))
            metadatas.append({"source": str(docfile), "chunk": unique_ids})
            document_chunks_ids.append(str(unique_ids))
            unique_ids += 1

        collection.add(
            ids=document_chunks_ids, embeddings=single_chunk_embed, metadatas=metadatas
        )
        assert collection.count() == len(metadatas)

        for i in range(0, len(metadatas)):
            query_result = collection.query(
                query_embeddings=single_chunk_embed[i],
                include=["metadatas", "embeddings"],
            )
            print(query_result)
            for ids, mdatas, embeddings in zip(
                query_result["ids"],
                query_result["metadatas"],
                query_result["embeddings"],
            ):
                for id, metadata, embedding in zip(ids, mdatas, embeddings):
                    assert id in document_chunks_ids
                    index = document_chunks_ids.index(id)
                    assert id == document_chunks_ids[index]
                    assert metadata == metadatas[index]
                    assert numpy.allclose(embedding, single_chunk_embed[index])
