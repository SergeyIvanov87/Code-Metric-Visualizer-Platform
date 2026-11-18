"""Document splitting shared by RAG processors."""

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
