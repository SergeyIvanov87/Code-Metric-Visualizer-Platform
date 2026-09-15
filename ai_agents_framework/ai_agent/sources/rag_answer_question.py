#!/usr/bin/env python

#https://docs.langchain.com/oss/python/deepagents/retrieval

from typing import Any

from pathlib import Path

import argparse
import json
import multiprocessing
import os
import sys

import chromadb

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.tools import tool
from langchain_community.chat_models import ChatLlamaCpp
from llama_cpp.llama_chat_format import Jinja2ChatFormatter
import requests
from tqdm import tqdm


from docs_retriever import DocumentStore
from embedding_model import get_embedding_model

from pydantic import BaseModel, Field

MAX_RETRIEVAL_RESULTS = 20
DEFAULT_RETRIEVAL_RESULTS = 5
MAX_ACCEPTABLE_DISTANCE = 1.0  # Initial value only; calibrate with your data.

from collections.abc import Callable

# some models do not reliably select tools automatically; its documentation recommends forcing the tool choice
# need to define middleware explicitly
from langchain.agents.middleware import (
    ModelRequest,
    ModelResponse,
    wrap_model_call,
)
from langchain.messages import ToolMessage

NULL_SAFE_QWEN_CHAT_TEMPLATE_PATH = Path(__file__).with_name(
    "qwen3_null_safe_chat_template.jinja"
)


def create_null_safe_qwen_chat_handler(
    chat_template_path: Path,
):
    """Create a llama.cpp handler from a null-safe Qwen Jinja template."""

    try:
        chat_template = chat_template_path.read_text(encoding="utf-8")
    except OSError as error:
        raise RuntimeError(
            f"Unable to load Qwen chat template: {chat_template_path}"
        ) from error

    if not chat_template.strip():
        raise RuntimeError(
            f"Qwen chat template is empty: {chat_template_path}"
        )

    return Jinja2ChatFormatter(
        template=chat_template,
        eos_token="<|im_end|>",
        bos_token="",
    ).to_chat_handler()


def load_null_safe_qwen_model(
    model_path: Path,
    chat_template_path: Path = NULL_SAFE_QWEN_CHAT_TEMPLATE_PATH,
) -> ChatLlamaCpp:
    """Load a Qwen GGUF with the standalone null-safe chat template."""

    chat_handler = create_null_safe_qwen_chat_handler(chat_template_path)

    return ChatLlamaCpp(
        model_path=str(model_path.as_posix()),
        temperature=0,
        max_tokens=1024,
        top_p=0.9,
        repeat_penalty=1.1,
        n_ctx=8192,
        n_batch=512,
        n_threads=max(1, multiprocessing.cpu_count() - 1),
        n_gpu_layers=-1,
        model_kwargs={"chat_handler": chat_handler},
        verbose=True,
    )


class KnowledgeSearchInput(BaseModel):
    query: str = Field(
        min_length=1,
        description="Semantic search query. Use concise keywords from the user's question.",
    )

    '''
    k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of results. Must be between 1 and 20; normally use 5.",
    )
    '''



def retrieve_by_vector(collection, query_embedder, document_store, query: str, k: int = 5) -> list[dict[str, Any]]:
    safe_k = min(max(int(k), 1), MAX_RETRIEVAL_RESULTS)

    if safe_k != k:
        print(
            f"[RETRIEVAL] Adjusted unsafe k={k!r} to {safe_k}",
            flush=True,
        )


    query_vector = query_embedder.embed_query(query)

    result = collection.query(
        query_embeddings=[query_vector],
        n_results=safe_k,
        include=["distances"],
    )

    ids = result["ids"][0]
    distances = result["distances"][0] if result["distances"] else []

    documents_by_id = document_store.get_many(ids)

    retrieved = []

    for position, document_id in enumerate(ids):
        distance = (
            distances[position]
            if position < len(distances)
            else None
        )
        if distance is None:
            continue

        if distance > MAX_ACCEPTABLE_DISTANCE:
            print(
                f"[RETRIEVAL] Rejecting id={document_id}: "
                f"distance={distance:.4f}, acceptable distance={MAX_ACCEPTABLE_DISTANCE:.4f}",
                flush=True,
            )
            continue

        content = documents_by_id.get(document_id)

        # Handles deleted or inaccessible external documents.
        if content is None:
            continue

        retrieved.append(
            {
                "id": document_id,
                "content": content,
                "distance": (
                    distances[position]
                    if position < len(distances)
                    else None
                ),
            }
        )

    return retrieved

def search_knowledge_base_impl(
    collection, query_embedder, document_store,
    query: str,
    k: int = 5,
) -> tuple[str, list[dict[str, Any]]]:
    """Search the private knowledge base for information relevant to a question."""

    records = []
    if not collection is None:
        records = retrieve_by_vector(
            collection=collection,
            query_embedder=query_embedder,
            document_store=document_store,
            query=query,
            k=k,
        )

    if not records:
        return "No relevant knowledge-base content was found.", []

    context_parts = []

    for record in records:
        context_parts.append(
            f"Source ID: {record['id']}\n"
            f"Content:\n{record['content']}"
        )

    model_content = "\n\n---\n\n".join(context_parts)

    artifacts = [
        {
            "document_id": record["id"],
            "distance": record["distance"],
        }
        for record in records
    ]

    return model_content, artifacts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="Agentic RAG")
    parser.add_argument(
        "-system_prompt",
        "--system_prompt",
        type=str,
        help="System prompt",
    )
    parser.add_argument(
        "-user_prompt",
        "--user_prompt",
        type=str,
        help="User prompt",
    )
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
        "-session_id",
        "--session_id",
        type=str,
        help="Session ID"
    )

    parser.add_argument(
        "shared_api_dir", type=Path, help="Root path of the mounted API dir"
    )
    parser.add_argument("main_service_name", type=str, help="the main service name")
    parser.add_argument("assets_models", help="Path to the root directory with models")
    args = parser.parse_args()

    chroma_client = chromadb.HttpClient(host=args.db_host, port=args.db_port)
    collection = None
    try:
        collection = chroma_client.get_collection(
            name=args.main_service_name,
        )
    except chromadb.errors.NotFoundError as ex:
        pass

    # This must be the same embedding model/configuration used when the
    # stored Chroma embeddings were generated.
    query_embedder = get_embedding_model()
    document_store = DocumentStore(args.shared_api_dir, args.main_service_name)

    #model_name = "llama-2-7b-chat.Q2_K.gguf"#"llama-2-7b-chat.Q4_K_M.gguf"#"Hermes-2-Pro-Llama-3-8B-GGUF"
    model_name = "Qwen3-4B-Q4_K_M.gguf"
    '''
    model = ChatOpenAI(
        model=model_name,
        temperature=0,
    )
    '''

    model_path = Path(args.assets_models) / model_name

    if not os.path.exists(model_path):
        print(f"Downloading {model_path}...")
        # You may want to replace the model URL by another of your choice
        #model_url = "https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/" + model_name
        #model_url = "https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/" + model_name
        model_url = "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/" + model_name
        model_url = "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf"
        response = requests.get(model_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))

        with open(model_path, 'wb') as f:
            for data in tqdm(response.iter_content(chunk_size=4096), total=total_size//4096):
                f.write(data)
        print("Download complete!")

    '''
    model = ChatLlamaCpp(
        model_path=str(model_path.as_posix()),

        # Generation
        temperature=0,
        max_tokens=1024,
        top_p=0.9,
        repeat_penalty=1.1,

        # Context and performance
        n_ctx=8192,
        n_batch=512,
        n_threads=max(1, multiprocessing.cpu_count() - 1),

        # Use -1 to attempt to offload all layers to the GPU.
        # Use 0 for CPU-only inference.
        n_gpu_layers=-1,

        verbose=True,
    )
    '''
    null_safe_qwen_model = load_null_safe_qwen_model(model_path)

    @tool(
        args_schema=KnowledgeSearchInput,
        response_format="content_and_artifact")
    def search_knowledge_base(
        query: str,
        #k: int = 5,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Search the private knowledge base for information relevant to a question."""
        print(
            f"[TOOL EXECUTED] query={query!r}, k={DEFAULT_RETRIEVAL_RESULTS}",
            flush=True,
        )

        return search_knowledge_base_impl(
            collection=collection,
            query_embedder=query_embedder,
            document_store=document_store,
            query=query,
            k=DEFAULT_RETRIEVAL_RESULTS,
        )

    print(
        json.dumps(
            search_knowledge_base.args_schema.model_json_schema(),
            indent=2,
        )
    )

    FORCED_RETRIEVAL_CHOICE = {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
        },
    }


    @wrap_model_call
    def force_initial_retrieval(
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Require one successful retrieval before allowing a final answer."""

        last_message = request.messages[-1] if request.messages else None

        if isinstance(last_message, ToolMessage):
            if last_message.status == "success":
                print(
                    "[MIDDLEWARE] Successful retrieval; allowing final answer",
                    flush=True,
                )
                return handler(request)

            error_count = sum(
                1
                for message in request.messages
                if (
                    isinstance(message, ToolMessage)
                    and message.name == "search_knowledge_base"
                    and message.status == "error"
                )
            )

            print(
                f"[MIDDLEWARE] Retrieval failed; error count={error_count}",
                flush=True,
            )

            if error_count >= 2:
                raise RuntimeError(
                    "Knowledge-base retrieval failed twice; "
                    "refusing to generate an ungrounded answer."
                )

            # Give the model the validation error and force it to try again.
            return handler(
                request.override(
                    tool_choice=FORCED_RETRIEVAL_CHOICE,
                )
            )

        print(
            "[MIDDLEWARE] Forcing search_knowledge_base",
            flush=True,
        )

        return handler(
            request.override(
                tool_choice=FORCED_RETRIEVAL_CHOICE,
            )
        )


    # TEST TESt TEST
    print("Testing retrieval tool directly...", flush=True)

    direct_result = search_knowledge_base.invoke(
        {
            "query": "What is Code Metric Visualizer Platform?",
          #  "k": 5,
        }
    )

    print("Direct retrieval result:", direct_result, flush=True)

    '''
    #TEst Test Test
    forced_model = model.bind_tools(
        [search_knowledge_base],
        tool_choice={
            "type": "function",
            "function": {
                "name": "search_knowledge_base",
            },
        },
    )

    probe = forced_model.invoke(
        "What is Code Metric Visualizer Platform?"
    )

    print(probe.tool_calls)
    print(probe.invalid_tool_calls)

    print("Model content:", probe.content, flush=True)
    print("Model tool calls:", probe.tool_calls, flush=True)
    print("Invalid tool calls:", probe.invalid_tool_calls, flush=True)

#    sys.exit(0)



    agent = create_agent(
        model=model,
        tools=[search_knowledge_base],
        middleware=[force_initial_retrieval],
        system_prompt = """
    You are a knowledge-base assistant.

    You must not answer knowledge-base questions from memory.

    A successful search_knowledge_base result is the only permitted source of
    factual information. A ToolMessage with status="error" contains no search
    results and must never be treated as evidence.

    After successful retrieval:
    - Answer only from the returned content.
    - Cite only Source IDs actually present in the returned content.
    - If no relevant content was returned, say that no relevant information was found.

    Never invent content or Source IDs.
    """,
        debug=True,
    )
'''

    """
    You are a knowledge-base assistant.

    You must not answer knowledge-base questions from memory.

    A successful search_knowledge_base result is the only permitted source of
    factual information. A ToolMessage with status="error" contains no search
    results and must never be treated as evidence.

    After successful retrieval:
    - Answer only from the returned content.
    - Cite only Source IDs actually present in the returned content.
    - If no relevant content was returned, say that no relevant information was found.

    Never invent content or Source IDs.
    """
    null_safe_qwen_agent = create_agent(
        model=null_safe_qwen_model,
        tools=[search_knowledge_base],
        middleware=[force_initial_retrieval],
        system_prompt = args.system_prompt,
        debug=True,
    )

    result = null_safe_qwen_agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": args.user_prompt,
                }
            ]
        }
    )

    print(result["messages"][-1].content)
