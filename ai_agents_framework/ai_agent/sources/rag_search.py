#!/usr/bin/env python

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_PARAMETERS = {
    "score_min": "0.0",
    "score_max": "1.0",
    "count": "5",
    "collection_use_regex": ".*",
    "collection_avoid_regex": "",
}


def parse_parameters(parameters: list[str]) -> dict[str, Any]:
    if len(parameters) % 2 != 0:
        raise ValueError("parameters must be provided as name/value pairs")

    parsed = dict(zip(parameters[::2], parameters[1::2]))
    expected = {"search", *DEFAULT_PARAMETERS}
    unexpected = set(parsed) - expected
    if unexpected:
        raise ValueError(f"unexpected parameters: {', '.join(sorted(unexpected))}")

    values = {**DEFAULT_PARAMETERS, **parsed}
    search = values.get("search", "")
    if not search.strip():
        raise ValueError("search must not be empty")

    try:
        score_min = float(values["score_min"])
        score_max = float(values["score_max"])
    except ValueError as error:
        raise ValueError("score_min and score_max must be numbers") from error
    if not math.isfinite(score_min) or not math.isfinite(score_max):
        raise ValueError("score_min and score_max must be finite")
    if score_min < 0 or score_max < 0:
        raise ValueError("score_min and score_max must not be negative")
    if score_min > score_max:
        raise ValueError("score_min must not be greater than score_max")

    try:
        count = int(values["count"])
    except ValueError as error:
        raise ValueError("count must be an integer") from error
    if count < 1:
        raise ValueError("count must be greater than zero")

    try:
        use_regex = re.compile(values["collection_use_regex"] or ".*")
        avoid_regex = (
            re.compile(values["collection_avoid_regex"])
            if values["collection_avoid_regex"]
            else None
        )
    except re.error as error:
        raise ValueError(f"invalid collection regex: {error}") from error

    return {
        "search": search,
        "score_min": score_min,
        "score_max": score_max,
        "count": count,
        "collection_use_regex": values["collection_use_regex"] or ".*",
        "collection_avoid_regex": values["collection_avoid_regex"],
        "use_regex": use_regex,
        "avoid_regex": avoid_regex,
    }


def collection_names(chroma_client) -> list[str]:
    """Support Chroma versions that return names or collection objects."""
    names = []
    for collection in chroma_client.list_collections():
        name = collection if isinstance(collection, str) else collection.name
        names.append(str(name))
    return sorted(set(names))


def select_collection_names(
    chroma_client, use_regex: re.Pattern, avoid_regex: re.Pattern | None
) -> list[str]:
    return [
        name
        for name in collection_names(chroma_client)
        if use_regex.search(name)
        and (avoid_regex is None or not avoid_regex.search(name))
    ]


def query_collection(
    collection,
    query_embedding: list[float],
    score_min: float,
    score_max: float,
    count: int,
) -> list[dict[str, Any]]:
    """Return enough in-range records without always requesting a whole collection."""
    collection_size = collection.count()
    if collection_size < 1:
        return []

    request_count = min(collection_size, count)
    while True:
        response = collection.query(
            query_embeddings=[query_embedding],
            n_results=request_count,
            include=["distances"],
        )
        ids = response.get("ids", [[]])[0]
        distances = response.get("distances", [[]])[0]
        matches = [
            {"id": str(record_id), "score": float(distance)}
            for record_id, distance in zip(ids, distances)
            if distance is not None and score_min <= float(distance) <= score_max
        ]

        last_distance = float(distances[-1]) if distances else None
        if (
            len(matches) >= count
            or request_count >= collection_size
            or (last_distance is not None and last_distance > score_max)
        ):
            return matches[:count]
        request_count = min(collection_size, max(request_count + 1, request_count * 2))


def search_chroma(
    chroma_client,
    query_embedder,
    document_store,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    selected = select_collection_names(
        chroma_client,
        parameters["use_regex"],
        parameters["avoid_regex"],
    )
    query_embedding = query_embedder.embed_query(parameters["search"])

    matches = []
    for name in selected:
        collection = chroma_client.get_collection(name=name)
        for match in query_collection(
            collection,
            query_embedding,
            parameters["score_min"],
            parameters["score_max"],
            parameters["count"],
        ):
            matches.append({"collection": name, **match})

    matches.sort(key=lambda item: (item["score"], item["collection"], item["id"]))
    matches = matches[: parameters["count"]]
    ids = list(dict.fromkeys(match["id"] for match in matches))
    content_by_id = document_store.get_many(ids)
    documents = [
        {**match, "content": content_by_id.get(match["id"])} for match in matches
    ]

    return {
        "error_code": 0,
        "error_msg": "success",
        "search": parameters["search"],
        "score_semantics": "raw Chroma distance; smaller values are closer matches",
        "score_min": parameters["score_min"],
        "score_max": parameters["score_max"],
        "collection_use_regex": parameters["collection_use_regex"],
        "collection_avoid_regex": parameters["collection_avoid_regex"],
        "collections": selected,
        "count": len(documents),
        "documents": documents,
    }


def main(
    shared_api_dir: Path,
    main_service_name: str,
    db_host: str,
    db_port: int,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    import chromadb

    from docs_retriever import DocumentStore
    from embedding_model import get_embedding_model

    chroma_client = chromadb.HttpClient(host=db_host, port=db_port)
    query_embedder = get_embedding_model()
    document_store = DocumentStore(shared_api_dir, main_service_name)
    return search_chroma(chroma_client, query_embedder, document_store, parameters)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="Search RAG directly")
    parser.add_argument("-db_host", "--db_host", required=True)
    parser.add_argument("-db_port", "--db_port", required=True, type=int)
    parser.add_argument("-session_id", "--session_id", required=True)
    parser.add_argument("shared_api_dir", type=Path)
    parser.add_argument("main_service_name")
    parser.add_argument("parameters", nargs="*")
    args = parser.parse_args()

    exit_code = 0
    try:
        result = main(
            args.shared_api_dir,
            args.main_service_name,
            args.db_host,
            args.db_port,
            parse_parameters(args.parameters),
        )
    except Exception as error:
        exit_code = 1
        result = {
            "error_code": exit_code,
            "error_msg": f"Couldn't search RAG documents, error: {error}",
        }
    print(json.dumps(result))
    sys.exit(exit_code)
