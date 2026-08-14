import json
import re
import socket

from distutils.version import StrictVersion
from pathlib import Path
from uuid import uuid4

from api_schema_utils import (
    gather_api_schemas_from_mount_point,
    compose_api_queries_pipe_names,
)
from api_fs_query import APIQueryInterruptible


def get_doc_dispatcher_queries(
    api_mount_point: Path, domain_name_api_entry: str
) -> dict:
    gathered_fs_API, _ = gather_api_schemas_from_mount_point(
        api_mount_point, domain_name_api_entry
    )
    return gathered_fs_API


def get_normalized_api_queries(
    shared_api_dir, main_service_name, query_normalizarion_map: dict
):
    api_queries = get_doc_dispatcher_queries(shared_api_dir, main_service_name)

    # Check API consistency
    if len(api_queries) == 0:
        raise RuntimeError(
            f"Cannot detect API queries by path: {shared_api_dir} and service name: {main_service_name}"
        )

    normalized_api_queries = {}
    for non_normalized_query_name, api_query in api_queries.items():
        for query_name, query_re in query_normalizarion_map.items():
            if query_re.match(non_normalized_query_name):
                normalized_api_queries[query_name] = (
                    get_last_query_version(
                        normalized_api_queries[query_name], api_query
                    )
                    if query_name in normalized_api_queries.keys()
                    else api_query
                )

    for normalized_query_name in query_normalizarion_map.keys():
        if normalized_query_name not in normalized_api_queries.keys():
            raise RuntimeError(
                f'Cannot find the query "{normalized_query_name}" among available API, available normailized queries: {normalized_api_queries.keys()}\n, non-normalized queries: \n{api_queries.keys()}'
            )
    return normalized_api_queries


def generate_inner_session_id(session_id_prefix):
    hostname = socket.gethostname()
    return f"{session_id_prefix}_{hostname}_rag_add_{uuid4().hex}"


def create_api_query_interruptible(shared_api_dir, query_json_description, session_id):
    query_pipes = compose_api_queries_pipe_names(
        shared_api_dir, query_json_description, session_id
    )

    query = APIQueryInterruptible(query_pipes, remove_session_pipe_on_result_done=False)
    if not query.is_valid():
        raise RuntimeError(f"The API query: {query_json_description} isn't ready")
    return query


def execute_put_doc_query(
    query: APIQueryInterruptible,
    session_id,
    timeout_elapsed,
    doc_uri,
    doc_data,
    doc_type,
    doc_metadata,
):
    exec_args_array = [
        f"SESSION_ID={session_id}",
        f"-URI={doc_uri}",
        f"-doc_type={doc_type}",
    ]

    if doc_metadata is not None:
        exec_args_array.append(f"-metadata={doc_metadata}")

    exec_args_array.append(f"doc_data={doc_data}")
    exec_args = " ".join(exec_args_array)

    status, timeout_elapsed = query.execute(timeout_elapsed, exec_args)
    if not status:
        raise RuntimeError(
            f"Cannot put the entire doc by URI: {doc_uri} into the rag_doc_dispater, status: {status}, elapsed timeout: {timeout_elapsed}"
        )

    # TODO Reconsile timeout_elapsed and wait for pipe creation sleep duration and cycles
    status, result, timeout_elapsed = query.wait_result(
        timeout_elapsed, session_id, 0.1, timeout_elapsed / 0.1, False
    )
    if not status:
        raise RuntimeError(
            f"Cannot put the entire doc by URI: {doc_uri} into the rag_doc_dispater: waiting of result failed, status: {status}, result: {result}, elapsed timeout: {timeout_elapsed}"
        )

    put_doc_result = json.loads(result)
    if put_doc_result["error_code"] != 0:
        raise RuntimeError(
            f"Cannot put the entire doc by URI: {doc_uri} into the rag_doc_dispater, error: {put_doc_result['error_msg']}"
        )

    assert (
        "unique_id" in put_doc_result.keys()
    ), "put_doc must return the 'unique_id' of the inserted document"
    return put_doc_result


def execute_attach_doc_chunks_query(
    query: APIQueryInterruptible,
    session_id,
    timeout_elapsed,
    doc_unique_id,
    doc_type,
    chunks_metadata,
    chunk_data_array,
):
    # execute query
    chunk_unique_ids = []
    chunk_metadata = []
    for chunk_num, ch in enumerate(chunk_data_array):
        exec_args_array = [
            f"SESSION_ID={session_id}",
            f"-doc_id={doc_unique_id}",
        ]
        single_chunk_metadata = str(chunk_num)
        if chunks_metadata is not None:
            single_chunk_metadata = f"{chunks_metadata}_{single_chunk_metadata}"

        exec_args_array.append(f"-metadata={single_chunk_metadata}")
        exec_args_array.append(f"doc_data={ch}")
        exec_args = " ".join(exec_args_array)

        status, timeout_elapsed = query.execute(timeout_elapsed, exec_args)
        if not status:
            raise RuntimeError(
                f"Cannot attach chunk num: {chunk_num} to the doc_id: {doc_unique_id} using the rag_doc_dispater, status: {status}, elapsed timeout: {timeout_elapsed}"
            )

        # TODO Reconsile timeout_elapsed and wait for pipe creation sleep duration and cycles
        status, result, timeout_elapsed = query.wait_result(
            timeout_elapsed, session_id, 0.1, timeout_elapsed / 0.1, False
        )
        if not status:
            raise RuntimeError(
                f"Cannot attach chunk num: {chunk_num} to the doc_id: {doc_unique_id} using the rag_doc_dispater: waiting of result failed, status: {status}, result: {result}, elapsed timeout: {timeout_elapsed}"
            )

        attach_chunk_result = json.loads(result)
        if attach_chunk_result["error_code"] != 0:
            raise RuntimeError(
                f"Cannot attach chunk num: {chunk_num} to the doc_id: {doc_unique_id} using the rag_doc_dispater, error: {attach_chunk_result['error_msg']}"
            )

        assert (
            "unique_id" in attach_chunk_result.keys()
        ), "attach_chunk must return the 'unique_id' of the inserted chunk"
        chunk_unique_ids.append(str(attach_chunk_result["unique_id"]))
        chunk_metadata.append(
            {
                "doc_id": doc_unique_id,
                "chunk_num": chunk_num,
                "chunk_id": attach_chunk_result["unique_id"],
            }
        )
    return chunk_unique_ids, chunk_metadata


def execute_delete_doc_query(
    query: APIQueryInterruptible,
    session_id,
    timeout_elapsed,
    doc_id,
    doc_metadata,
):
    exec_args = " ".join(
        [
            f"SESSION_ID={session_id}",
            f"-id={doc_id}",
            f"-metadata={doc_metadata}",
        ]
    )
    status, timeout_elapsed = query.execute(timeout_elapsed, exec_args)
    if not status:
        raise RuntimeError(
            f"Cannot delete the doc by id: {doc_id} using the rag_doc_dispater, status: {status}, elapsed timeout: {timeout_elapsed}, session: {session_id}"
        )

    # TODO Reconsile timeout_elapsed and wait for pipe creation sleep duration and cycles
    status, result, timeout_elapsed = query.wait_result(
        timeout_elapsed, session_id, 0.1, timeout_elapsed / 0.1, False
    )
    if not status:
        raise RuntimeError(
            f"Cannot delete the doc by id: {doc_id} using the rag_doc_dispater: waiting of result failed, status: {status}, result: {result}, elapsed timeout: {timeout_elapsed}, session: {session_id}"
        )

    delete_doc_result = json.loads(result)
    if delete_doc_result["error_code"] != 0:
        raise RuntimeError(
            f"Cannot delete the doc by id: {doc_id} using the rag_doc_dispater, error: {delete_doc_result['error_msg']}"
        )

    return delete_doc_result


def get_last_query_version(api_query_lhs, api_query_rhs):
    lhs = Path(api_query_lhs["Query"]).name
    rhs = Path(api_query_rhs["Query"]).name

    valid_version_re = re.compile(r"^(v\d*(\.\d+)*)$")
    if not valid_version_re.match(lhs):
        raise RuntimeError(
            f"get_last_query_version failed as lhs has incorrect version: {lhs}, check: {api_query_lhs}"
        )
    if not valid_version_re.match(rhs):
        raise RuntimeError(
            f"get_last_query_version failed as rhs has incorrect version: {rhs}, check: {api_query_rhs}"
        )
    return (
        api_query_lhs
        if StrictVersion(lhs[1:]) >= StrictVersion(rhs[1:])
        else api_query_rhs
    )
