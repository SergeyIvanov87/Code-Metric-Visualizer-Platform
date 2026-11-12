"""Exercise empty metadata through the generated delete executor."""

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from api_fs_args import write_args
from api_fs_conventions import get_api_request_plain_params


@pytest.mark.parametrize("metadata", [None, "", 'team docs "quoted"'])
def test_delete_executor_preserves_empty_metadata(tmp_path, metadata):
    root = Path("/repo")
    source = root / "ai_agents_framework/ai_agent"
    schema = json.loads((source / "API/rag_delete.json").read_text())
    api = tmp_path / "api"
    api.mkdir()
    write_args(api, get_api_request_plain_params(schema["Params"]))

    # Parse the generated argv so a dangling -metadata fails as in rag_delete.py.
    processor = tmp_path / "rag_delete.py"
    processor.write_text(
        f"#!{sys.executable}\n"
        "import argparse,json\n"
        "parser=argparse.ArgumentParser()\n"
        "parser.add_argument('-ids', required=True)\n"
        "parser.add_argument('-metadata')\n"
        "parser.add_argument('--session_id', required=True)\n"
        "parser.add_argument('-db_host', required=True)\n"
        "parser.add_argument('-db_port', required=True)\n"
        "parser.add_argument('shared_api_dir')\n"
        "parser.add_argument('main_service_name')\n"
        "print(json.dumps(vars(parser.parse_args())))\n"
    )
    processor.chmod(0o755)
    spec = importlib.util.spec_from_file_location("delete_generator", source / "sources/api_generator.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    script = io.StringIO()
    generator.make_script_rag_delete(script, "json")
    command = "SESSION_ID=delete-test -ids=12,13"
    if metadata is not None:
        command += " -metadata=" + json.dumps(metadata)
    completed = subprocess.run(
        ["bash", "-c", script.getvalue(), "executor", str(api), command],
        env={**os.environ, "WORK_DIR": str(tmp_path), "SHARED_API_DIR": "/api",
             "MAIN_SERVICE_NAME": "domain", "VECTOR_DB_HOST": "db", "VECTOR_DB_PORT": "8000"},
        text=True, capture_output=True, check=True,
    )
    result = json.loads(completed.stdout)
    assert result["metadata"] == ("" if metadata is None else metadata)
    assert result["ids"] == "12,13"
    assert result["session_id"] == "delete-test"
    assert result["shared_api_dir"] == "/api"
    assert result["main_service_name"] == "domain"
