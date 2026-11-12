"""HTTP ambassador: schema-derived presentation and filesystem API adaptation."""

from concurrent.futures import ThreadPoolExecutor
import errno
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import shutil
import tempfile
import threading
from uuid import uuid4

from flask import Flask, g, jsonify, render_template, request
from markdown import markdown
from werkzeug.exceptions import HTTPException

from api_fs_query import APIQueryInterruptible
from api_schema_utils import compose_api_queries_pipe_names

DISCOVERY_PATH = "/.well-known/http-api-routes/v1"
HELP_PATH = "/help"

BULK_UPLOAD_TEMPORARY_PREFIX = ".http-ambassador-incoming-"
TRANSPORT_PARAMETERS = {
    "SESSION_ID",
    "WaitInitialQueryTimeoutSec",
    "WaitQueryUpdateTimeoutSec",
    "WaitResultConsumptionTimeoutSec",
}
SUPPORTED_SCHEMAS = {
    "chat": {
        "method": "POST",
        "template": "chat.html",
        "script": "chat.js",
        "navigation_label": "Chat with the knowledge base",
    },
    "rag_add": {
        "method": "PUT",
        "template": "rag_add.html",
        "script": "rag_add.js",
        "navigation_label": "Add a document to the knowledge base",
    },
    "rag_bulk_add": {
        "method": "POST",
        "template": "rag_bulk_add.html",
        "script": "rag_bulk_add.js",
        "navigation_label": "Add files and folders to the knowledge base",
        "bulk_upload": True,
        "page_parameter_defaults": {"WaitQueryUpdateTimeoutSec": "60"},
    },
}


class APIUnavailable(RuntimeError):
    pass


class APIQueryTimeout(RuntimeError):
    """The operation may have been accepted; callers must not retry it blindly."""


class InvalidAPIResult(RuntimeError):
    pass


def load_schemas(schema_dir):
    schemas = {}
    for path in sorted(Path(schema_dir).glob("*.json")):
        schema = json.loads(path.read_text())
        if "Query" not in schema:
            continue
        missing = {"Method", "Params"} - schema.keys()
        if missing:
            raise ValueError(
                f"Filesystem API schema {path.name} is missing: "
                + ", ".join(sorted(missing))
            )
        if not isinstance(schema["Params"], dict):
            raise ValueError(f"Filesystem API schema {path.name} has invalid Params")
        schemas[path.stem] = schema
    return schemas


def build_discovery_document(schemas, timeout_seconds):
    route_timeout = float(timeout_seconds) + 10
    if route_timeout.is_integer():
        route_timeout = int(route_timeout)
    routes = sorted(
        (
            {"path": "/" + schema["Query"].lstrip("/"), "timeout_seconds": route_timeout}
            for schema in schemas.values()
        ),
        key=lambda route: route["path"],
    )
    routes.append({"path": HELP_PATH, "timeout_seconds": route_timeout})
    routes.sort(key=lambda route: route["path"])
    revision = hashlib.sha256(
        json.dumps(routes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {"schema_version": 1, "revision": "sha256:" + revision, "routes": routes}


def quote_argument_value(value):
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if "\0" in value:
        raise ValueError("Filesystem API arguments cannot contain NUL")
    value = value.replace("\r\n", "\n").replace("\n", "\r")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def serialize_arguments(arguments, session_id):
    forwarded = dict(arguments)
    forwarded["SESSION_ID"] = session_id
    return " ".join(
        f"{name}={quote_argument_value(value)}"
        for name, value in forwarded.items()
    )


def display_default(params):
    for value in params.values():
        if isinstance(value, list):
            value = "\n".join(str(part) for part in value)
        if isinstance(value, str) and value:
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            return value.replace('\\"', '"').replace("\\\\", "\\")
    return ""


def result_failed(result):
    return result.get("error_code") not in (None, 0, "0", False)


def create_app(config_path=None, query_factory=None):
    config_path = config_path or os.environ.get(
        "AI_AGENT_HTTP_CONFIG", str(Path(__file__).with_name("config.json"))
    )
    settings = json.loads(Path(config_path).read_text())
    main_menu_path = os.environ["MAIN_MENU_PATH"]
    if not main_menu_path.startswith("/") or main_menu_path.startswith("//"):
        raise ValueError("MAIN_MENU_PATH must be a root-relative path")

    api_mount = Path(settings["api_mount"])
    available_schemas = load_schemas(settings["schema_dir"])
    missing_schemas = SUPPORTED_SCHEMAS.keys() - available_schemas.keys()
    if missing_schemas:
        raise ValueError(
            "Missing filesystem API schemas: " + ", ".join(sorted(missing_schemas))
        )

    schemas = {name: available_schemas[name] for name in SUPPORTED_SCHEMAS}
    supported_queries = {schema["Query"] for schema in schemas.values()}
    unsupported_queries = sorted(
        str(schema["Query"])
        for schema in available_schemas.values()
        if schema["Query"] not in supported_queries
    )
    if unsupported_queries:
        raise ValueError(
            "Unsupported filesystem API queries: " + ", ".join(unsupported_queries)
        )

    for name, schema in schemas.items():
        support = SUPPORTED_SCHEMAS[name]
        if (
            schema.get("Content-Type") != "application/json"
            or schema.get("Method") != support["method"]
        ):
            raise ValueError(f"Unsupported {name} filesystem API schema")
        unknown_page_defaults = (
            support.get("page_parameter_defaults", {}).keys() - schema["Params"].keys()
        )
        if unknown_page_defaults:
            raise ValueError(f"Unsupported {name} page parameter defaults")

    for key in ("timeout_seconds", "max_upload_bytes", "max_result_bytes"):
        if not isinstance(settings[key], (int, float)) or settings[key] <= 0:
            raise ValueError(f"{key} must be positive")

    query_factory = query_factory or APIQueryInterruptible
    timeout_seconds = float(settings["timeout_seconds"])
    max_result_bytes = int(settings["max_result_bytes"])
    paths = {name: "/" + schema["Query"].lstrip("/") for name, schema in schemas.items()}
    write_locks = {
        schema["Query"]: threading.Lock()
        for schema in schemas.values()
    }
    sessions = threading.local()

    service_root = Path(__file__).resolve().parent
    page_style = (service_root / "static/style.css").read_text()
    readme_html = markdown(
        (service_root / "README.md").read_text(),
        extensions=("fenced_code", "tables"),
    )
    page_scripts = {
        name: (service_root / "static" / support["script"]).read_text()
        for name, support in SUPPORTED_SCHEMAS.items()
    }
    discovery_document = build_discovery_document(schemas, timeout_seconds)

    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = int(settings["max_upload_bytes"])

    def make_query(schema):
        pipes = compose_api_queries_pipe_names(str(api_mount), schema)
        return query_factory(pipes, remove_session_pipe_on_result_done=False)

    def execute(schema, arguments, reuse_session=True):
        if "preserveOriginal" in schema["Params"]:
            # HTTP uploads are staged input owned by this ingestion request.
            # Ignore client overrides and explicitly request transfer of ownership.
            arguments = {"preserveOriginal": "0", **{
                name: value for name, value in arguments.items()
                if name != "preserveOriginal"
            }}
        query = make_query(schema)
        if not query.is_valid():
            raise APIUnavailable(
                f"Filesystem API {schema['Query']} is not ready"
            )

        session_id = (
            getattr(sessions, "completed", None) if reuse_session else None
        ) or "http_" + uuid4().hex
        sessions.completed = None
        command = serialize_arguments(arguments, session_id)

        with write_locks[schema["Query"]]:
            sent, remaining = query.execute(timeout_seconds, command)
        if not sent or remaining <= 0:
            raise APIQueryTimeout(
                "Filesystem API write deadline exceeded; completion is unknown"
            )

        wait_result = query.wait_result(
            remaining,
            session_id,
            0.1,
            max(1, math.ceil(remaining / 0.1)),
            False,
        )
        if not wait_result or not wait_result[0]:
            raise APIQueryTimeout(
                "Filesystem API result deadline exceeded; completion is unknown"
            )

        raw = wait_result[1]
        if len(raw.encode("utf-8")) > max_result_bytes:
            raise InvalidAPIResult("Filesystem API result exceeds configured limit")
        if reuse_session:
            sessions.completed = session_id

        try:
            result = json.loads(raw)
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            raise InvalidAPIResult("Filesystem API returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise InvalidAPIResult("Filesystem API returned a non-object result")
        return result

    def upload_document(schema):
        filename = request.args.get("filename", "")
        if not filename or filename in (".", "..") or "/" in filename or "\0" in filename:
            raise ValueError("filename must be a nonempty file name")
        staging_root = api_mount / ".http-document-uploads"
        staging_root.mkdir(mode=0o755, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix="document-", dir=staging_root))
        directory.chmod(0o777)
        source = directory / filename
        retain_source = False
        try:
            with source.open("wb") as stream:
                shutil.copyfileobj(request.stream, stream)
            source.chmod(0o644)
            arguments = {"URI": str(source)}
            for name in ("metadata", "doc_type", "timeout"):
                if name in request.args:
                    arguments[name] = request.args[name]
            result = execute(schema, arguments)
            return jsonify(result), 502 if result_failed(result) else 200
        except (APIQueryTimeout, InvalidAPIResult):
            # The processor may still consume the source after the HTTP request.
            retain_source = True
            raise
        finally:
            if not retain_source:
                shutil.rmtree(directory)

    def bulk_request_paths(schema, upload_id):
        if not re.fullmatch(r"deferred-[A-Za-z0-9_-]+", upload_id or ""):
            raise FileNotFoundError("Bulk upload session was not found")
        root = api_mount / schema["Query"] / schema["Method"]
        request_directory = root / upload_id
        report_path = request_directory / "stage.json"
        if not request_directory.is_dir() or not report_path.is_file():
            raise FileNotFoundError("Bulk upload session is no longer available")
        report = json.loads(report_path.read_text())
        return {
            "request": request_directory,
            "input": request_directory / "input",
            "events": request_directory / "events",
            "result": request_directory / "async_result",
            "seal": Path(report["uploader_request"]) / "seal",
        }

    def bulk_start(schema):
        arguments = request.get_json(silent=True)
        if not isinstance(arguments, dict):
            return jsonify(error="Expected a JSON object of filesystem API parameters"), 400
        result = execute(schema, arguments, reuse_session=False)
        if result_failed(result):
            return jsonify(result), 502
        required = {"input", "events", "result", "protocol"}
        if not required.issubset(result):
            raise InvalidAPIResult("Bulk filesystem API returned an invalid readiness report")
        upload_id = Path(result["input"]).parent.name
        return jsonify(upload_id=upload_id, protocol=result["protocol"])

    def safe_upload_relative_path(value):
        if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
            raise ValueError("Upload path must be a nonempty POSIX relative path")
        relative = PurePosixPath(value)
        if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
            raise ValueError("Upload path must remain below the bulk input directory")
        return relative

    def bulk_upload_file(schema):
        if request.mimetype != "application/octet-stream":
            return jsonify(error="Bulk file uploads require application/octet-stream"), 415
        upload_id = request.args.get("upload_id", "")
        relative = safe_upload_relative_path(request.args.get("path", ""))
        paths_for_request = bulk_request_paths(schema, upload_id)
        stage = paths_for_request["input"].resolve(strict=True)
        destination = stage.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        resolved_parent = destination.parent.resolve(strict=True)
        if not resolved_parent.is_relative_to(stage):
            raise ValueError("Upload path escaped the bulk input directory")

        incoming = stage.parent / f"{BULK_UPLOAD_TEMPORARY_PREFIX}{upload_id}"
        try:
            incoming.mkdir(mode=0o700)
        except FileExistsError:
            pass
        incoming_info = incoming.lstat()
        if (not stat.S_ISDIR(incoming_info.st_mode)
                or incoming_info.st_uid != os.geteuid()
                or incoming.resolve(strict=True).parent != stage.parent):
            raise ValueError("Bulk upload temporary directory is unsafe")
        temporary = incoming / uuid4().hex
        written = 0
        try:
            with temporary.open("xb") as output:
                while True:
                    chunk = request.stream.read(64 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    written += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError:
                return jsonify(error=f"Upload path already exists: {relative.as_posix()}"), 409
            temporary.unlink()
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        return jsonify(path=relative.as_posix(), bytes=written)

    def bulk_finish(schema):
        upload_id = request.args.get("upload_id", "")
        paths_for_request = bulk_request_paths(schema, upload_id)
        stage = paths_for_request["input"].resolve(strict=True)
        incoming = stage.parent / f"{BULK_UPLOAD_TEMPORARY_PREFIX}{upload_id}"
        with ThreadPoolExecutor(max_workers=1) as pool:
            events_future = pool.submit(
                APIQueryInterruptible.read_fifo,
                paths_for_request["events"],
                timeout_seconds,
                max_result_bytes,
            )
            sealed, _ = APIQueryInterruptible.write_fifo(
                paths_for_request["seal"],
                min(timeout_seconds, 5),
                b"seal\n",
            )
            result_status, raw_result, _ = APIQueryInterruptible.read_fifo(
                paths_for_request["result"],
                timeout_seconds,
                max_result_bytes,
            )
            events_status, raw_events, _ = events_future.result()

        if not result_status or not events_status:
            detail = "seal or result" if not sealed else "result"
            raise APIQueryTimeout(
                f"Bulk upload {detail} deadline exceeded; completion is unknown"
            )
        try:
            result = json.loads(raw_result.decode())
            events = [
                json.loads(line)
                for line in raw_events.decode().splitlines()
                if line.strip()
            ]
        except (UnicodeDecodeError, ValueError) as exc:
            raise InvalidAPIResult("Bulk filesystem API returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise InvalidAPIResult("Bulk filesystem API returned a non-object result")
        try:
            incoming.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            if exc.errno != errno.ENOTEMPTY:
                app.logger.warning(
                    "Could not remove bulk upload temporary directory %s: %s",
                    incoming,
                    exc,
                )
        return jsonify(result=result, events=events), 502 if result_failed(result) else 200

    @app.before_request
    def request_nonce():
        g.csp_nonce = uuid4().hex

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return jsonify(error=exc.description), exc.code

    @app.errorhandler(ValueError)
    def bad_request(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(APIUnavailable)
    def unavailable(exc):
        return jsonify(error=str(exc)), 503

    @app.errorhandler(APIQueryTimeout)
    def timeout(exc):
        return jsonify(error=str(exc), completion_unknown=True), 504

    @app.errorhandler(InvalidAPIResult)
    def invalid_result(exc):
        return jsonify(error=str(exc)), 502

    @app.errorhandler(FileNotFoundError)
    def missing_upload(exc):
        return jsonify(error=str(exc)), 410

    @app.errorhandler(OSError)
    def io_error(exc):
        app.logger.exception("Filesystem API I/O failed")
        return jsonify(error="Filesystem API I/O failed"), 503

    @app.route(DISCOVERY_PATH, methods=["GET"], strict_slashes=False)
    def http_api_routes_discovery():
        return jsonify(discovery_document)

    @app.route("/healthz", methods=["GET"])
    def health():
        ready = all(make_query(schema).is_valid() for schema in schemas.values())
        return jsonify(ready=ready), 200 if ready else 503

    @app.route(HELP_PATH, methods=["GET"], strict_slashes=False)
    def help_page():
        navigation = [
            {"path": paths[name], "label": support["navigation_label"]}
            for name, support in SUPPORTED_SCHEMAS.items()
        ]
        return render_template(
            "help.html",
            main_menu_path=main_menu_path,
            navigation=navigation,
            csp_nonce=g.csp_nonce,
            page_style=page_style,
            readme_html=readme_html,
        )

    def render_page(name, schema):
        support = SUPPORTED_SCHEMAS[name]
        request_parameters = dict(schema["Params"])
        request_parameters.pop("preserveOriginal", None)
        request_parameters.update(support.get("page_parameter_defaults", {}))
        navigation = [
            {"path": paths[other_name], "label": support["navigation_label"]}
            for other_name, support in SUPPORTED_SCHEMAS.items()
            if other_name != name
        ]
        hidden_parameters = (
            {"SESSION_ID"} if support.get("bulk_upload")
            else TRANSPORT_PARAMETERS
        )
        page_parameters = {
            parameter: default
            for parameter, default in request_parameters.items()
            if parameter not in hidden_parameters
        }
        concurrency_parameter = next(
            (
                parameter
                for parameter, default in page_parameters.items()
                if str(default).isdigit() and 1 <= int(default) <= 32
            ),
            None,
        )
        return render_template(
            SUPPORTED_SCHEMAS[name]["template"],
            main_menu_path=main_menu_path,
            help_path=HELP_PATH,
            navigation=navigation,
            csp_nonce=g.csp_nonce,
            page_style=page_style,
            page_script=page_scripts[name],
            request_method=schema["Method"],
            request_parameters=request_parameters,
            page_parameters=page_parameters,
            concurrency_parameter=concurrency_parameter,
            default_prompt=display_default(schema["Params"]),
        )

    def make_view(name, schema):
        support = SUPPORTED_SCHEMAS[name]

        def view():
            if request.method == "GET":
                return render_page(name, schema)
            if support.get("bulk_upload"):
                if request.method == schema["Method"]:
                    return bulk_start(schema)
                if request.method == "PUT":
                    return bulk_upload_file(schema)
                if request.method == "PATCH":
                    return bulk_finish(schema)

            if name == "rag_add" and request.mimetype == "application/octet-stream":
                return upload_document(schema)
            arguments = request.get_json(silent=True)
            if name == "rag_add" and isinstance(arguments, dict) and "doc_data" in arguments:
                raise ValueError("Document uploads require a file body or a URI")
            if not isinstance(arguments, dict):
                return jsonify(error="Expected a JSON object of filesystem API parameters"), 400
            try:
                result = execute(schema, arguments)
            except ValueError as exc:
                return jsonify(error=str(exc)), 400
            return jsonify(result), 502 if result_failed(result) else 200

        view.__name__ = f"{name}_view"
        return view

    for name, schema in schemas.items():
        methods = ["GET", schema["Method"]]
        if SUPPORTED_SCHEMAS[name].get("bulk_upload"):
            methods.extend(["PUT", "PATCH"])
        app.add_url_rule(
            paths[name],
            endpoint=f"{name}_endpoint",
            view_func=make_view(name, schema),
            methods=methods,
            strict_slashes=False,
        )

    return app
