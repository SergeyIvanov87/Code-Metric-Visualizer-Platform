import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

SERVICE = Path(__file__).resolve().parents[1]
REPO = SERVICE.parents[2]
sys.path[:0] = [str(SERVICE), str(REPO / "common"), str(REPO / "common/modules")]

from api_fs_args import write_args
from api_fs_conventions import get_api_request_plain_params
from build_api_services import create_cli_server_content_from_schema
from server import create_app


@pytest.fixture
def filesystem_api(tmp_path):
    """Real generated CLI servers/executors; replace only the heavy ML programs."""
    api = tmp_path / "api"
    api.mkdir()
    spec = importlib.util.spec_from_file_location("agent_api_generator", REPO / "ai_agents_framework/ai_agent/sources/api_generator.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    stub = f"#!{sys.executable}\n" + '''
import json
import sys
from pathlib import Path

def value(key):
    return sys.argv[sys.argv.index(key) + 1]

if Path(sys.argv[0]).name == "agentic_rag.py":
    print(json.dumps({"response": value("-user_prompt"), "system_prompt": value("-system_prompt")}))
else:
    uri = value("-URI")
    print(json.dumps({"error_code": 0, "doc_id": "fixture-document", "chunk_ids": ["fixture-chunk"], "document": Path(uri).read_text(), "uri": uri, "doc_type": value("-doc_type")}))
'''
    for filename in ("agentic_rag.py", "rag_add.py"):
        path = scripts / filename
        path.write_text(stub)
        path.chmod(0o755)
    processes = []
    logs = []
    schemas = {}
    env = dict(os.environ, SHARED_API_DIR=str(api), WORK_DIR=str(scripts), VECTOR_DB_HOST="fixture", VECTOR_DB_PORT="8000", MAIN_SERVICE_NAME="fixture", ASSET_MODELS="fixture")
    try:
        for name in ("chat", "rag_add"):
            schema = json.loads((REPO / f"ai_agents_framework/ai_agent/API/{name}.json").read_text())
            schemas[name] = schema
            node = api / schema["Query"]
            (node / schema["Method"]).mkdir(parents=True)
            write_args(node, get_api_request_plain_params(schema["Params"]))
            executor = scripts / f"{name}_exec.sh"
            with executor.open("w") as output:
                getattr(generator, f"make_script_{name}")(output, "json")
            executor.chmod(0o755)
            server = scripts / f"{name}_server.sh"
            server.write_text("#!/bin/bash\n" + "".join(create_cli_server_content_from_schema(name, schema, str(scripts))))
            log = (tmp_path / f"{name}.log").open("w")
            logs.append(log)
            processes.append(subprocess.Popen(["bash", str(server)], env=env, stdout=log, stderr=log, start_new_session=True))
        deadline = time.monotonic() + 5
        while not all((api / schema["Query"] / schema["Method"] / "result.json").exists() for schema in schemas.values()):
            assert time.monotonic() < deadline, "Generated filesystem APIs did not start"
            time.sleep(0.01)
        config = tmp_path / "http.json"
        config.write_text(json.dumps({"api_mount": str(api), "schema_dir": str(REPO / "ai_agents_framework/ai_agent/API"), "timeout_seconds": 30, "max_upload_bytes": 1024 * 1024, "max_prompt_bytes": 65536, "max_result_bytes": 1024 * 1024}))
        yield api, schemas, config
    finally:
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        for log in logs:
            log.close()


@pytest.fixture
def app(filesystem_api):
    return create_app(filesystem_api[2])
