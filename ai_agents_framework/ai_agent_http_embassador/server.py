"""HTTP ambassador: query-specific presentation and filesystem API adaptation."""

import codecs
import json
import os
from pathlib import Path
import re
import shutil
from uuid import uuid4

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from fifo_client import FifoClient, InvalidResult, QueryTimeout, Unavailable


MAIN_MENU_PATH = "/api.pmccabe_collector.restapi.org"


def create_app(config_path=None, client=None):
    config_path = config_path or os.environ.get("AI_AGENT_HTTP_CONFIG", str(Path(__file__).with_name("config.json")))
    settings = json.loads(Path(config_path).read_text())
    api_mount = Path(settings["api_mount"]).resolve()
    agent_mount = Path(settings.get("agent_api_mount", settings["api_mount"]))
    # rag_add's existing executor uses xargs + sh -c. Only generated, shell-safe
    # paths and metadata are allowed through that executor.
    for mount in (api_mount, agent_mount):
        if not mount.is_absolute() or not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(mount)) or ".." in mount.parts:
            raise ValueError("API mount paths must be absolute, shell-safe paths")
    schema_dir = Path(settings["schema_dir"])
    schemas = {name: json.loads((schema_dir / f"{name}.json").read_text()) for name in ("chat", "rag_add")}
    for name, method in (("chat", "POST"), ("rag_add", "PUT")):
        if schemas[name]["Method"] != method or schemas[name].get("Content-Type") != "application/json":
            raise ValueError(f"Unsupported {name} filesystem API schema")
    for key in ("timeout_seconds", "max_upload_bytes", "max_prompt_bytes", "max_result_bytes"):
        if not isinstance(settings[key], (int, float)) or settings[key] <= 0:
            raise ValueError(f"{key} must be positive")
    client = client or FifoClient(api_mount, settings["timeout_seconds"], settings["max_result_bytes"])
    paths = {name: "/" + schema["Query"] for name, schema in schemas.items()}
    for schema in schemas.values():
        FifoClient(api_mount).node(schema)  # Validate paths even with a test client.
    prompt = schemas["chat"]["Params"]["-system_prompt"]
    prompt = "\n".join(prompt) if isinstance(prompt, list) else prompt
    # Schema quotes are CLI grouping delimiters, not part of the system prompt.
    if prompt.startswith('"') and prompt.endswith('"'):
        prompt = prompt[1:-1]
    prompt = prompt.replace('\\"', '"').replace("\\\\", "\\")
    app = Flask(__name__, static_url_path="/ai-agent-ui/static")
    app.config["MAX_CONTENT_LENGTH"] = int(settings["max_upload_bytes"])

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return jsonify(error=exc.description), exc.code

    @app.after_request
    def response_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'"
        return response

    def execute(name, args):
        raw = client.execute(schemas[name], args)
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise InvalidResult("Filesystem API returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise InvalidResult("Filesystem API returned a non-object result")
        return result

    @app.errorhandler(Unavailable)
    def unavailable(exc):
        return jsonify(error=str(exc)), 503

    @app.errorhandler(QueryTimeout)
    def timeout(exc):
        return jsonify(error=str(exc), completion_unknown=True), 504

    @app.errorhandler(InvalidResult)
    def invalid_result(exc):
        return jsonify(error=str(exc)), 502

    @app.errorhandler(OSError)
    def io_error(exc):
        app.logger.exception("Filesystem API I/O failed")
        return jsonify(error="Filesystem API I/O failed"), 503

    @app.route("/ai-agent-ui/healthz", methods=["GET"])
    @app.route("/healthz", methods=["GET"])
    def health():
        ready = all(client_path_ready(schema) for schema in schemas.values())
        return jsonify(ready=ready), 200 if ready else 503

    def client_path_ready(schema):
        node = FifoClient(api_mount).node(schema)
        return FifoClient._fifo(node / "exec") and FifoClient._fifo(node / "result.json")

    @app.route(paths["chat"], methods=["GET", "POST"], strict_slashes=False)
    def chat():
        if request.method == "GET":
            return render_template(
                "chat.html",
                main_menu_path=MAIN_MENU_PATH,
                system_prompt=prompt,
                upload_path=paths["rag_add"],
            )
        data = request.get_json()
        if not isinstance(data, dict) or set(data) - {"user_prompt", "system_prompt"}:
            return jsonify(error="Expected user_prompt and optional system_prompt"), 400
        user_prompt = data.get("user_prompt")
        system_prompt = data.get("system_prompt", prompt)
        if not isinstance(user_prompt, str) or not user_prompt.strip() or not isinstance(system_prompt, str):
            return jsonify(error="Prompts must be strings; user_prompt must be nonempty"), 400
        if "\0" in user_prompt + system_prompt:
            return jsonify(error="Prompts cannot contain NUL"), 400
        try:
            prompt_size = len((user_prompt + system_prompt).encode("utf-8"))
        except UnicodeEncodeError:
            return jsonify(error="Prompts must contain valid Unicode"), 400
        if prompt_size > settings["max_prompt_bytes"]:
            return jsonify(error="Prompts exceed configured size limit"), 413
        result = execute("chat", {"-user_prompt": user_prompt, "-system_prompt": system_prompt})
        if "response" not in result and not result.get("error_code"):
            raise InvalidResult("Chat result has no response")
        return jsonify(result), 502 if result.get("error_code") else 200

    @app.route(paths["rag_add"], methods=["GET", "PUT"], strict_slashes=False)
    def rag_add():
        if request.method == "GET":
            return render_template(
                "rag_add.html",
                chat_path=paths["chat"],
                main_menu_path=MAIN_MENU_PATH,
            )
        if request.mimetype != "application/octet-stream":
            return jsonify(error="Send the file bytes as application/octet-stream"), 415
        token = uuid4().hex
        relative = Path(".http_embassador") / "staging" / token
        # Ensure all new ancestors are traversable by the agent's distinct UID,
        # including when this server was launched with a restrictive umask.
        for parent in (api_mount / ".http_embassador", api_mount / ".http_embassador/staging"):
            parent.mkdir(mode=0o755, exist_ok=True)
            parent.chmod(0o755)
        directory = api_mount / relative
        directory.mkdir(parents=True, mode=0o755)
        directory.chmod(0o755)
        staged_file = directory / "document.txt"
        retain = False
        try:
            decoder = codecs.getincrementaldecoder("utf-8")()
            size = 0
            with staged_file.open("xb") as output:
                staged_file.chmod(0o644)  # ai_agent has a different container UID.
                while chunk := request.stream.read(65536):
                    size += len(chunk)
                    if size > settings["max_upload_bytes"]:
                        return jsonify(error="Upload exceeds configured size limit"), 413
                    decoder.decode(chunk)
                    output.write(chunk)
                decoder.decode(b"", final=True)
            if not size:
                return jsonify(error="The selected file is empty"), 400
            try:
                result = execute("rag_add", {
                    "-URI": str(agent_mount / relative / staged_file.name),
                    "-doc_type": "txt",
                    "-metadata": "http_upload_" + token,
                })
            except (QueryTimeout, InvalidResult, OSError):
                retain = True  # The agent may still be using this file.
                raise
            if "error_code" not in result or (not result["error_code"] and "doc_id" not in result):
                raise InvalidResult("rag_add result has no error_code or document ID")
            return jsonify(result), 502 if result.get("error_code") else 200
        except UnicodeDecodeError:
            return jsonify(error="rag_add currently supports UTF-8 text files"), 415
        finally:
            if not retain:
                shutil.rmtree(directory)

    return app
