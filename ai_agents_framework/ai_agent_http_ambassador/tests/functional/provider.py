"""FIFO provider for testing the real HTTP ambassador container."""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import api_generator
from api_fs_args import write_args
from api_fs_conventions import get_api_request_plain_params
from api_fs_exec_utils import generate_exec_header, generate_api_node_env_init
from build_api_services import create_cli_server_content_from_schema


work = Path("/work")
for name in ("rag_add_data.py", "agentic_rag.py", "stub.py"):
    target = work / name
    shutil.copyfile("/stub.py", target)
    target.chmod(0o755)
env = dict(os.environ, VECTOR_DB_HOST="stub", VECTOR_DB_PORT="8000",
           MAIN_SERVICE_NAME="stub", ASSET_MODELS="stub")
processes = []


def stop(*_args):
    for process in processes:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
    raise SystemExit(0)


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
for name in ("chat", "rag_add_data", "rag_bulk_add"):
    schema = json.loads((Path("/schemas") / f"{name}.json").read_text())
    node = Path("/api") / schema["Query"]
    (node / schema["Method"]).mkdir(parents=True, exist_ok=True)
    write_args(node, get_api_request_plain_params(schema["Params"]))
    executor = work / f"{name}_exec.sh"
    with executor.open("w") as output:
        if name == "rag_add_data":
            # Exercise production flag conversion without running ML models.
            api_generator.make_script_rag_add_data(output, "json")
        else:
            body = [*generate_exec_header(), *generate_api_node_env_init(),
                    f'"${{WORK_DIR}}/stub.py" {name} "${{IN_SERVER_REQUEST_ARGS[@]}}"']
            output.write("\n".join(body) + "\n")
    executor.chmod(0o755)
    server = work / f"{name}_server.sh"
    server.write_text("#!/bin/bash\n" + "".join(
        create_cli_server_content_from_schema(name, schema, str(work))))
    processes.append(subprocess.Popen(["bash", str(server)], env=env, start_new_session=True))

while True:
    if any(process.poll() is not None for process in processes):
        raise RuntimeError("FIFO provider stopped unexpectedly")
    time.sleep(0.1)
