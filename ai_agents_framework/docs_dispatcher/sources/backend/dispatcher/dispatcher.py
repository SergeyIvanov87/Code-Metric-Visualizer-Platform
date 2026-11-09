"""Command delegation and response formatting for a configured backend."""

import json
import subprocess
import sys

from .config import load_backend_config


class BackendDispatcher:
    def __init__(self):
        self._config = load_backend_config()

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
            cwd=self._config.backends_code_dir,
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
