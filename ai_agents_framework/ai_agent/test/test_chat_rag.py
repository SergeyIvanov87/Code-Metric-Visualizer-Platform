"""Black-box functional tests for the ai_agent filesystem API."""

import base64
import json
import os
from pathlib import Path
from uuid import uuid4

from api_fs_query import APIQueryInterruptible
from api_schema_utils import compose_api_queries_pipe_names
from utils import get_api_queries


API_SCHEMAS = get_api_queries("/API", os.environ["MAIN_SERVICE_NAME"])
DATA_DIR = Path("/tests/data")
QUESTION = "What is the RRD microservice?"


def execute_api(
    api_dir: str, query_schema: dict, arguments: dict[str, str], timeout: float = 900
) -> str:
    """Execute a public filesystem API with a bounded, interruptible query."""
    session_id = f"ai_agent_test_{uuid4().hex}"
    pipes = compose_api_queries_pipe_names(api_dir, query_schema, session_id)
    query = APIQueryInterruptible(pipes, remove_session_pipe_on_result_done=True)
    command = " ".join(
        [
            f"SESSION_ID={session_id}",
            *(f"{key}={value}" for key, value in arguments.items()),
        ]
    )

    status, remaining = query.execute(timeout, command)
    assert status, f"API did not accept the query within {timeout} seconds"
    status, result, _ = query.wait_result(remaining, session_id, 0.1, 9000, True)
    assert status, f"API did not return a result within {timeout} seconds"
    return result.strip()


def add_document(path: Path) -> dict:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    result = json.loads(
        execute_api(
            os.environ["SHARED_API_DIR"],
            API_SCHEMAS["rag_add"],
            {
                "-metadata": f"functional_test_{path.stem}",
                "-doc_type": "txt",
                "doc_data": encoded,
            },
        )
    )
    assert result["error_code"] == 0, result
    assert result["doc_id"]
    assert result["chunk_ids"]
    return result


def ask_rrd_question() -> str:
    # Values contain no shell quotes: the generated file API preserves the
    # complete values after splitting each key=value argument at its first '='.
    return execute_api(
        os.environ["SHARED_API_DIR"],
        API_SCHEMAS["chat"],
        {
            "-system_prompt": (
                "Use only retrieved knowledge-base content. If there is no relevant "
                "content, say that you do not have information about the subject."
            ),
            "-user_prompt": QUESTION,
        },
        timeout=300,
    )


def test_chat_becomes_grounded_after_readme_is_added():
    distractors = sorted(DATA_DIR.glob("poem_*.txt"))
    assert len(distractors) == 12
    for document in distractors:
        add_document(document)

    ungrounded_answer = ask_rrd_question().lower()
    assert any(
        phrase in ungrounded_answer
        for phrase in ("no relevant", "do not have information", "don't have information")
    ), ungrounded_answer

    add_document(DATA_DIR / "README.md")
    grounded_answer = ask_rrd_question().lower()
    assert "round-robin" in grounded_answer or "round robin" in grounded_answer
    assert "metric" in grounded_answer
    assert any(word in grounded_answer for word in ("accumulat", "store", "database"))
