import json
import os

from utils import compose_api_queries_pipe_names
from utils import get_api_queries
from utils import wait_until_pipe_exist

class FS_API_Executor:
    def __init__(self, api_json_schema_directory, fs_api_mount_directory, api_domain_name):
        self.api_json_schema_directory = api_json_schema_directory
        self.fs_api_mount_directory = fs_api_mount_directory

        self.registered_queries = get_api_queries(api_json_schema_directory, api_domain_name)
        if len(self.registered_queries) == 0:
            raise RuntimeError(f"No any API queries by domain name: {api_domain_name}, were found by path: {api_json_schema_directory}")

    def execute(self, query_name, query_params = "0", session_id = ""):
        if not query_name in self.registered_queries.keys():
            raise RuntimeError(f"Query: {query_name} is not registered in the list: {str(', ').join(self.registered_queries.keys())}")

        out = ""
        api_pipes = compose_api_queries_pipe_names(self.fs_api_mount_directory, self.registered_queries[query_name], session_id)
        with open(api_pipes[0], "w") as pin:
            pin.write(query_params)
        wait_until_pipe_exist(api_pipes[1])
        with open(api_pipes[1], "r") as pout:
            out = pout.read()

        # remove temporal pipe unless it's main session id
        if len(session_id) != 0:
            os.remove(api_pipes[1])
        return out
