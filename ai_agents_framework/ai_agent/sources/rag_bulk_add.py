#!/usr/bin/env python3
"""Bridge streaming-directory upload events to the regular RAG add query."""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import time
from uuid import uuid4

from directory_event_protocol import parse_directory_event_stream


DEFAULTS = {
    "metadata": "", "WaitInitialQueryTimeoutSec": "60",
    "WaitQueryUpdateTimeoutSec": "10", "WaitResultConsumptionTimeoutSec": "60",
    "SESSION_ID": "default",
}
CODE_EXTENSIONS = {
    "c", "cc", "cpp", "cxx", "h", "hpp", "cs", "go", "java", "js", "jsx",
    "kt", "kts", "lua", "php", "pl", "py", "r", "rb", "rs", "scala", "sh",
    "sql", "swift", "ts", "tsx", "vue", "zig",
}
TEXT_GROUPS = {
    "markdown": {"md", "markdown", "rst", "adoc"},
    "data": {"csv", "json", "jsonl", "toml", "tsv", "xml", "yaml", "yml"},
    "web": {"css", "htm", "html", "scss", "svg"},
    "document": {"log", "text", "txt"},
}
stopping = False


def stop(_signal, _frame):
    global stopping
    stopping = True


def values(arguments):
    if len(arguments) % 2:
        raise ValueError("query arguments must be name/value pairs")
    result = dict(DEFAULTS)
    for index in range(0, len(arguments), 2):
        name = arguments[index].lstrip("-")
        if name not in DEFAULTS:
            raise ValueError(f"unsupported query parameter: {arguments[index]}")
        result[name] = arguments[index + 1]
    if not re.fullmatch(r"[A-Za-z0-9_.:@+-]{1,128}", result["SESSION_ID"]):
        raise ValueError("SESSION_ID must contain 1-128 safe characters")
    return result


def document_type(path):
    """Return a text-compatible semantic document type for a filename."""
    extension = Path(path).suffix.lower().lstrip(".")
    if extension in CODE_EXTENSIONS:
        return "txt,code"
    for group, extensions in TEXT_GROUPS.items():
        if extension in extensions:
            return f"txt,{group}"
    return f"txt,{extension or 'document'}"


def augmented_metadata(original, relative):
    tokens = ",".join(PurePosixPath(relative).parts)
    return ",".join(value for value in (original.strip(), tokens) if value)


def fifo_request(exec_fifo, arguments, session, timeout=10):
    """Execute a filesystem API query and return its session result."""
    exec_fifo = Path(exec_fifo)
    suffix = f"_{session}"
    candidates = [path for path in exec_fifo.parent.glob("result*") if "_" not in path.name]
    if not candidates:
        raise RuntimeError(f"no result FIFO beside {exec_fifo}")
    result_fifo = Path(str(sorted(candidates)[0]) + suffix)
    deadline = time.monotonic() + timeout
    descriptor = None
    while descriptor is None and time.monotonic() < deadline:
        try:
            descriptor = os.open(exec_fifo, os.O_WRONLY | os.O_NONBLOCK)
        except OSError:
            time.sleep(0.05)
    if descriptor is None:
        raise TimeoutError(f"query is not accepting requests: {exec_fifo}")
    try:
        os.write(descriptor, (arguments.rstrip() + "\n").encode())
    finally:
        os.close(descriptor)
    while time.monotonic() < deadline:
        if result_fifo.exists() and stat.S_ISFIFO(result_fifo.stat().st_mode):
            with result_fifo.open() as stream:
                return stream.read()
        time.sleep(0.05)
    raise TimeoutError(f"query result was not created: {result_fifo}")


def api_exec(root, relative):
    path = Path(root) / "api.pmccabe_collector.restapi.org" / relative
    if not path.is_fifo():
        raise ValueError(f"required filesystem API query is unavailable: {path}")
    return path


def start_uploader(request, config):
    root = os.environ.get("SHARED_API_DIR", "/api")
    uploader_exec = api_exec(root, "file-uploader/streaming_directory_events/POST/exec")
    session = f"rag-bulk-{config['SESSION_ID']}-{uuid4().hex}"
    arguments = " ".join((
        f"SESSION_ID={session}",
        f"WaitInitialQueryTimeoutSec={config['WaitInitialQueryTimeoutSec']}",
        f"WaitQueryUpdateTimeoutSec={config['WaitQueryUpdateTimeoutSec']}",
        f"WaitResultConsumptionTimeoutSec={config['WaitResultConsumptionTimeoutSec']}",
    ))
    report = json.loads(fifo_request(uploader_exec, arguments, session))
    (request / "uploader.json").write_text(json.dumps(report))
    return report


def prepare(request, arguments):
    config = values(arguments)
    report = start_uploader(request, config)
    stage = Path(report["staging"]).resolve(strict=True)
    input_path = request / "input"
    input_path.symlink_to(os.path.relpath(stage, request), target_is_directory=True)
    events = request / "events"
    os.mkfifo(events, 0o640)
    events.chmod(0o640)
    client_gid = os.environ.get("FS_API_CLIENT_GID")
    if client_gid is not None:
        os.chown(events, -1, int(client_gid))
    return {
        "input": str(input_path), "input_type": "DIRECTORY", "staging": str(stage),
        "events": str(events), "events_type": "FIFO",
        "protocol": "cmvp.rag-bulk-events.v1",
        "uploader_request": str(Path(report["events"]).parent),
    }


def publish_event(descriptor, event, timeout=1):
    payload = json.dumps(event, separators=(",", ":")).encode() + b"\n"
    deadline = time.monotonic() + timeout
    while not stopping and time.monotonic() < deadline:
        try:
            if descriptor[0] is None:
                descriptor[0] = os.open(descriptor[1], os.O_WRONLY | os.O_NONBLOCK)
            os.write(descriptor[0], payload)
            return True
        except OSError:
            if descriptor[0] is not None:
                os.close(descriptor[0])
                descriptor[0] = None
            time.sleep(0.05)
    return False


def add_file(config, stage, relative, sequence):
    root = os.environ.get("SHARED_API_DIR", "/api")
    rag_exec = api_exec(root, "ai_agent/rag/add_doc/v1/PUT/exec")
    session = f"rag-bulk-add-{config['SESSION_ID']}-{uuid4().hex}"
    uri = stage / relative
    metadata = augmented_metadata(config["metadata"], relative)
    arguments = " ".join((f"SESSION_ID={session}", f"-URI={json.dumps(str(uri))}",
                          f"-metadata={json.dumps(metadata)}",
                          f"-doc_type={document_type(relative)}"))
    result = json.loads(fifo_request(rag_exec, arguments, session, timeout=300))
    succeeded = result.get("error_code") in (0, "0")
    return {
        "sequence": sequence, "status": "added" if succeeded else "failed",
        "path": relative, "doc_type": document_type(relative),
        "doc_id": result.get("doc_id", ""), "rag_result": result,
    }


def run(options, arguments):
    config = values(arguments)
    report = json.loads((options.request_directory / "stage.json").read_text())
    uploader = json.loads((options.request_directory / "uploader.json").read_text())
    stage = Path(report["staging"])
    writer = [None, Path(report["events"])]
    added, failed = [], []
    sequence = 0
    with Path(uploader["events"]).open() as stream:
        for event in parse_directory_event_stream(stream):
            if event.get("status") != "ready":
                continue
            sequence += 1
            try:
                outcome = add_file(config, stage, event["path"], sequence)
            except Exception as error:
                outcome = {"sequence": sequence, "status": "failed",
                           "path": event.get("path", ""), "doc_id": "",
                           "error": str(error)}
            (added if outcome["status"] == "added" else failed).append(outcome)
            publish_event(writer, outcome)
    terminal = {"sequence": sequence + 1, "status": "terminated",
                "added_count": len(added), "failed_count": len(failed)}
    publish_event(writer, terminal)
    if writer[0] is not None:
        os.close(writer[0])
    print(json.dumps({"error_code": "0" if not failed else "1",
                      "added": added, "failed": failed}, separators=(",", ":")))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-directory", required=True, type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check-arguments", action="store_true")
    modes.add_argument("--prepare-api-channel", action="store_true")
    parser.add_argument("--initial-timeout", type=float)
    parser.add_argument("--update-timeout", type=float)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    arguments = options.arguments[1:] if options.arguments[:1] == ["--"] else options.arguments
    try:
        values(arguments)
        if options.check_arguments:
            print('{"error_code":"0","error_description":""}')
            return 0
        if options.prepare_api_channel:
            report = prepare(options.request_directory.resolve(strict=True), arguments)
            (options.request_directory / "stage.json").write_text(json.dumps(report))
            print(json.dumps(report))
            return 0
        return run(options, arguments)
    except Exception as error:
        print(json.dumps({"error_code": "1", "error_description": str(error)}))
        return 1


if __name__ == "__main__":
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    raise SystemExit(main())
