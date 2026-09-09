#!/usr/bin/python

# The original code has taken from here
# https://machinelearningmastery.com/building-a-rag-pipeline-with-llama-cpp-in-python/

import argparse
import os
from pathlib import Path
#import langchain.embeddings import HuggingFaceEmbeddings
import langchain.embeddings
#from langchain.vectorstores import Chroma
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
#from langchain.chains import RetrievalQA
from langchain_classic.chains import RetrievalQA
#from langchain.prompts import PromptTemplate
from langchain_core.prompts import PromptTemplate
#from langchain.llms import LlamaCpp
from langchain_community.llms import LlamaCpp
import requests
from tqdm import tqdm
import time

def foo(assets_models: str):
    model_name = "llama-2-7b-chat.Q4_K_M.gguf"
    model_path = Path(assets_models) / model_name

    if not os.path.exists(model_path):
        print(f"Downloading {model_path}...")
        # You may want to replace the model URL by another of your choice
        model_url = "https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/" + model_name
        response = requests.get(model_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))

        with open(model_path, 'wb') as f:
            for data in tqdm(response.iter_content(chunk_size=4096), total=total_size//4096):
                f.write(data)
        print("Download complete!")


    # Sample text for demonstration purposes
    with open("docs/sample.txt", "w") as f:
        f.write("""
        Retrieval-Augmented Generation (RAG) is a technique that combines retrieval-based and generation-based approaches
        for natural language processing tasks. It involves retrieving relevant information from a knowledge base and then
        using that information to generate more accurate and informed responses.

        RAG models first retrieve documents that are relevant to a given query, then use these documents as additional context
        for language generation. This approach helps to ground the model's responses in factual information and reduces hallucinations.

        The llama.cpp library is a C/C++ implementation of Meta's LLaMA model, optimized for CPU usage. It allows running LLaMA models
        on consumer hardware without requiring high-end GPUs.

        LocalAI is a framework that enables running AI models locally without relying on cloud services. It provides APIs compatible
        with OpenAI's interfaces, allowing developers to use their own models with the same code they would use for OpenAI services.
        """)

    documents = []
    for file in os.listdir("docs"):
        if file.endswith(".pdf"):
            loader = PyPDFLoader(os.path.join("docs", file))
            documents.extend(loader.load())
        elif file.endswith(".txt"):
            loader = TextLoader(os.path.join("docs", file))
            documents.extend(loader.load())

    # Split documents into chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len
    )

    chunks = text_splitter.split_documents(documents)

    #embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    embeddings =  langchain.embeddings.init_embeddings(model = "all-MiniLM-L6-v2",
                                                       provider = "huggingface")

    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory="./chroma_db"
    )

    llm = LlamaCpp(
        model_path=model_path.as_posix(),
        temperature=0.7,
        max_tokens=2000,
        n_ctx=4096,
        verbose=False
    )

    template = """
    Answer the question based on the following context:

    {context}

    Question: {question}
    Answer:
    """
    prompt = PromptTemplate(
        template=template,
        input_variables=["context", "question"]
    )

    rag_pipeline = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=vectorstore.as_retriever(search_kwargs={"k": 3}),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt}
    )


    def ask_question(question):
        start_time = time.time()
        result = rag_pipeline({"query": question})
        end_time = time.time()

        print(f"Question: {question}")
        print(f"Answer: {result['result']}")
        print(f"Time taken: {end_time - start_time:.2f} seconds")
        print("\nSource documents:")
        for i, doc in enumerate(result["source_documents"]):
            print(f"Document {i+1}:")
            print(f"Source: {doc.metadata.get('source', 'Unknown')}")
            print(f"Content: {doc.page_content[:150]}...\n")

    ask_question("What is RAG and how does it work?")
    ask_question("What is llama.cpp?")
    ask_question("How does LocalAI relate to cloud AI services?")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="main"
    )
    parser.add_argument("assets_models", help="Path to the root directory with models")
    args = parser.parse_args()

    foo(args.assets_models)
