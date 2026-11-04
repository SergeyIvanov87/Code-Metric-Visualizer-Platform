#!/usr/bin/env python

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb

from docs_retriever import DocumentStore
from embedding_model import get_embedding_model


@dataclass(frozen=True)
class SearchParameters:
    search: str
    score_min: float = 0.0
    score_max: float = 1.0
    count: int = 5
    collection_use_regex: str = ".*"
    collection_avoid_regex: str = ""


def _compile_collection_regex(value: str, parameter_name: str) -> re.Pattern:
    try:
        return re.compile(value)
    except re.error as error:
        raise ValueError(f"invalid {parameter_name}: {error}") from error


def parse_parameters(parameters: list[str]) -> SearchParameters:
    """Parse filesystem-API name/value pairs and validate search controls."""
    if len(parameters) % 2 != 0:
        raise ValueError("parameters must be provided as name/value pairs")

    values = dict(zip(parameters[::2], parameters[1::2]))
    expected = {
        "search",
        "score_min",
        "score_max",
        "count",
        "collection_use_regex",
        "collection_avoid_regex",
    }
    unexpected = set(values) - expected
    if unexpected:
        raise ValueError(
            f"unexpected parameters: {', '.join(sorted(unexpected))}"
        )

    search = values.get("search", "").strip()
    if not search:
        raise ValueError("search must not be empty")

    try:
        score_min = float(values.get("score_min", "0.0"))
        score_max = float(values.get("score_max", "1.0"))
    except ValueError as error:
        raise ValueError("score_min and score_max must be numbers") from error
    if not math.isfinite(score_min) or not math.isfinite(score_max):
        raise ValueError("score_min and score_max must be finite")
    if score_min < 0 or score_max < 0:
        raise ValueError("score_min and score_max must not be negative")
    if score_min > score_max:
        raise ValueError("score_min must not be greater than score_max")

    try:
        count = int(values.get("count", "5"))
    except ValueError as error:
        raise ValueError("count must be an integer") from error
    if count <= 0:
        raise ValueError("count must be greater than zero")

    use_regex = values.get("collection_use_regex", ".*")
    avoid_regex = values.get("collection_avoid_regex", "")
    _compile_collection_regex(use_regex, "collection regex")
    if avoid_regex:
        _compile_collection_regex(avoid_regex, "collection regex")

    return SearchParameters(
        search=search,
        score_min=score_min,
        score_max=score_max,
        count=count,
        collection_use_regex=use_regex,
        collection_avoid_regex=avoid_regex,
    )


def _collection_name(collection: Any) -> str:
    return collection if isinstance(collection, str) else collection.name


def _query_collection(
    collection,
    query_embedding: list[float],
    parameters: SearchParameters,
) -> list[tuple[float, str]]:
    """Retrieve enough nearest neighbors to satisfy a bounded distance range."""
    collection_size = collection.count()
    if collection_size <= 0:
        return []

    requested = min(parameters.count, collection_size)
    matches: list[tuple[float, str]] = []
    while requested:
        response = collection.query(
            query_embeddings=[query_embedding],
            n_results=requested,
            include=["distances"],
        )
        ids = (response.get("ids") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]
        matches = [
            (float(distance), str(record_id))
            for record_id, distance in zip(ids, distances)
            if distance is not None
            and parameters.score_min <= float(distance) <= parameters.score_max
        ]

        if len(matches) >= parameters.count or requested >= collection_size:
            break
        requested = min(collection_size, max(requested + 1, requested * 2))

    return matches


def search_chroma(
    chroma_client,
    query_embedder,
    document_store,
    parameters: SearchParameters,
) -> dict[str, Any]:
    """Search selected Chroma collections and return globally ranked chunks."""
    include = re.compile(parameters.collection_use_regex)
    avoid = (
        re.compile(parameters.collection_avoid_regex)
        if parameters.collection_avoid_regex
        else None
    )
    collection_names = sorted(
        _collection_name(collection)
        for collection in chroma_client.list_collections()
    )
    selected_names = [
        name
        for name in collection_names
        if include.search(name) and not (avoid and avoid.search(name))
    ]

    query_embedding = query_embedder.embed_query(parameters.search)
    candidates: list[tuple[float, str, str]] = []
    for name in selected_names:
        collection = chroma_client.get_collection(name=name)
        candidates.extend(
            (score, name, record_id)
            for score, record_id in _query_collection(
                collection, query_embedding, parameters
            )
        )

    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    candidates = candidates[: parameters.count]
    record_ids = [record_id for _, _, record_id in candidates]
    contents = document_store.get_many(record_ids) if record_ids else {}
    documents = [
        {
            "collection": collection_name,
            "id": record_id,
            "score": score,
            "content": contents.get(record_id, ""),
        }
        for score, collection_name, record_id in candidates
    ]
    return {
        "error_code": 0,
        "error_msg": "success",
        "collections": selected_names,
        "count": len(documents),
        "documents": documents,
    }


def main(
    shared_api_dir: Path,
    main_service_name: str,
    db_host: str,
    db_port: int,
    parameters: SearchParameters,
) -> dict[str, Any]:
    chroma_client = chromadb.HttpClient(host=db_host, port=db_port)
    query_embedder = get_embedding_model()
    document_store = DocumentStore(shared_api_dir, main_service_name)
    return search_chroma(
        chroma_client, query_embedder, document_store, parameters
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="Search RAG directly")
    parser.add_argument("-db_host", "--db_host", required=True)
    parser.add_argument("-db_port", "--db_port", required=True, type=int)
    parser.add_argument("-session_id", "--session_id")
    parser.add_argument("shared_api_dir", type=Path)
    parser.add_argument("main_service_name")
    parser.add_argument("parameters", nargs="*")
    args = parser.parse_args()

    exit_code = 0
    try:
        parsed_parameters = parse_parameters(args.parameters)
        result = main(
            args.shared_api_dir,
            args.main_service_name,
            args.db_host,
            args.db_port,
            parsed_parameters,
        )
    except Exception as error:
        exit_code = 1
        result = {
            "error_code": exit_code,
            "error_msg": f"Couldn't search RAG documents, error: {error}",
            "collections": [],
            "count": 0,
            "documents": [],
        }
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(exit_code)
