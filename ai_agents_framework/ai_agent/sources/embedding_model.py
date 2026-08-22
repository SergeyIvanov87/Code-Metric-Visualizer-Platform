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
