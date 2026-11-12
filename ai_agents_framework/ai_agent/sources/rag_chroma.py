"""Chroma insertion shared by RAG processors."""


def insert_embeddings(db_host, db_port, collection_name, chunk_ids, embeddings, metadata):
    import chromadb
    from langchain_chroma import Chroma
    client = chromadb.HttpClient(host=db_host, port=db_port)
    vectordb_client = Chroma(client=client)
    collection = client.get_or_create_collection(name=collection_name)
    collection.add(ids=chunk_ids, embeddings=embeddings, metadatas=metadata)
