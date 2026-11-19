#!/usr/bin/env python

from langchain_huggingface import HuggingFaceEmbeddings

def get_embedding_model():
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
    return embedding_model

'''
Consider the usage of fastembed

import chromadb
from fastembed import TextEmbedding

# 1. Initialize your lightweight embedding model
embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

# Your manually created chunks
chunks = [
    "This is the first text chunk.",
    "This is the second text chunk.",
]

# 2. Generate embeddings (returns a generator, convert to list)
embeddings = list(embedding_model.embed(chunks))

# 3. Connect to Chroma and add them
client = chromadb.Client()  # or PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="my_collection")

collection.add(
    documents=chunks,
    embeddings=embeddings,  # Pass your pre-computed vectors here
    ids=["id1", "id2"],
)
'''
