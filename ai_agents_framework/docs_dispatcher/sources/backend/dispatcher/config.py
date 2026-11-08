#!/usr/bin/env python

import json
import os
import subprocess
import sys

from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS_DIR = Path("/etc/dispatcher")
BUNDLED_SETTINGS_DIR = Path(__file__).resolve().parent
BACKENDS_CODE_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class BackendDispatcher:
    name: str
    settings_dir: Path
    spec_path: Path
    backends_code_dir: Path = BACKENDS_CODE_DIR

    def command_module(self, command_name: str) -> str:
        return f"dispatcher.commands.{command_name}"

    def create_executable_command_prefix(self, api_query_name):
        return [
            sys.executable,
            "-m",
            self.command_module(api_query_name)
        ]

    def delegate_query(self, command: list[str],
                       *,
                       input_data: bytes | str | None = None,
                       text: bool = True):
        exec_status = subprocess.run(
            command,
            input=input_data,
            capture_output=True,
            cwd=self.backends_code_dir,
            text=text,
            shell=False,
        )
        return exec_status

    def get_formatted_response(self,
                               exec_status, api_query_name,
                               *,
                               text: bool = True):
        return_data = {'error_code' : exec_status.returncode}
        err_str = exec_status.stderr if text else exec_status.stderr.decode('utf-8')
        if err_str:
            return_data["error_code"] = -1
            return_data["error_msg"] = err_str

        output_str = exec_status.stdout if text else exec_status.stdout.decode('utf-8')
        output = {}
        if output_str:
            try:
                output = json.loads(output_str)
            except Exception as ex:
                return_data["error_code"] = -1
                return_data["error_msg"] = f"The query {api_query_name} using assigned backend couldn't decode string as a valid JSON obj: {output_str}"

        return_data = return_data | output
        return return_data

def load_backend_config() -> BackendDispatcher:
    settings_dir = _select_settings_dir()
    spec_path = _current_backend_spec_path(settings_dir)
    spec = _load_yaml_mapping(spec_path)

    return BackendDispatcher(
        name=_required_string(spec, "name"),
        settings_dir=settings_dir,
        spec_path=spec_path,
    )


def _select_settings_dir() -> Path:
    configured_dir = Path(os.environ.get("DISPATCHER_SETTINGS_DIR", DEFAULT_SETTINGS_DIR))
    current_path = configured_dir / "current"
    if configured_dir.is_dir() and os.environ.get("DISPATCHER_BACKEND"):
        return configured_dir
    if current_path.exists() or current_path.is_symlink():
        return configured_dir
    return BUNDLED_SETTINGS_DIR


def _current_backend_spec_path(settings_dir: Path) -> Path:
    selected_backend = os.environ.get("DISPATCHER_BACKEND")
    if selected_backend:
        if not selected_backend.isidentifier():
            raise ValueError(f"Invalid dispatcher backend name: {selected_backend}")
        return settings_dir / "backends" / f"{selected_backend}.yaml"
    current_path = settings_dir / "current"
    if current_path.is_symlink():
        return current_path.resolve()

    if not current_path.exists():
        raise FileNotFoundError(f"Dispatcher current backend specification is missing: {current_path}")

    return current_path


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        loaded = _parse_yaml_mapping(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Dispatcher backend specification is missing: {path}") from exc

    if not isinstance(loaded, dict):
        raise ValueError(f"Dispatcher backend specification must be a YAML mapping: {path}")
    return loaded


def _parse_yaml_mapping(content: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"Invalid YAML mapping line {line_number}: {raw_line}")

        key, value = line.split(":", 1)
        key = key.strip()
        value = _strip_yaml_scalar(value.strip())
        if not key:
            raise ValueError(f"Invalid YAML mapping line {line_number}: empty key")
        parsed[key] = value
    return parsed


def _strip_yaml_scalar(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _required_string(spec: dict[str, Any], key: str) -> str:
    value = spec.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Dispatcher backend specification requires a non-empty string field: {key}")
    return value
