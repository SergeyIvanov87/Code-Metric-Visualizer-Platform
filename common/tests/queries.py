import json
import os

from api_schema_utils import compose_api_queries_pipe_names
from utils import get_api_queries
from utils import wait_until_pipe_exist
from api_fs_query import APIQuery
from api_fs_query import APIQueryInterruptible

class FS_API_Executor:
    def __init__(self, api_json_schema_directory, fs_api_mount_directory, api_domain_name):
        self.api_json_schema_directory = api_json_schema_directory
        self.fs_api_mount_directory = fs_api_mount_directory

        self.registered_queries = get_api_queries(api_json_schema_directory, api_domain_name)
        if len(self.registered_queries) == 0:
            raise RuntimeError(f"No any API queries by domain name: {api_domain_name}, were found by path: {api_json_schema_directory}")

    def wait_until_valid(self, query_name, session_id = "", sleep_between_cycles=0.1, max_cycles_count=30, console_ping = False):
        if not query_name in self.registered_queries.keys():
            raise RuntimeError(f"Query: {query_name} is not registered in the list: {str(', ').join(self.registered_queries.keys())}")

        query = APIQuery(compose_api_queries_pipe_names(self.fs_api_mount_directory, self.registered_queries[query_name], session_id))
        return query.wait_until_valid(sleep_between_cycles, max_cycles_count, console_ping)

    def execute(self, query_name, query_params = "0", session_id = ""):
        if not query_name in self.registered_queries.keys():
            raise RuntimeError(f"Query: {query_name} is not registered in the list: {str(', ').join(self.registered_queries.keys())}")

        query = APIQuery(compose_api_queries_pipe_names(self.fs_api_mount_directory, self.registered_queries[query_name], session_id))
        if len(session_id) != 0 and query_params.find("SESSION_ID=") == -1:
            if query_params == "0":
                query_params = f"SESSION_ID={session_id}"
            else:
                query_params += f"SESSION_ID={session_id}"
        query.execute(query_params)
        return query.wait_result(session_id, 0.1, 30, True)


class FS_API_AsyncExecutor(FS_API_Executor):
    def __init__(self, api_json_schema_directory, fs_api_mount_directory, api_domain_name):
        super().__init__(api_json_schema_directory, fs_api_mount_directory, api_domain_name)

    def wait_until_valid(self, query_name, session_id = "", sleep_between_cycles=0.1, max_cycles_count=30, console_ping = False):
        if not query_name in self.registered_queries.keys():
            raise RuntimeError(f"Query: {query_name} is not registered in the list: {str(', ').join(self.registered_queries.keys())}")

        query = APIQuery(compose_api_queries_pipe_names(self.fs_api_mount_directory, self.registered_queries[query_name], session_id))
        return query.wait_until_valid(sleep_between_cycles, max_cycles_count, console_ping)

    def execute(self, query_name, query_params = "0", session_id = "", exec_timeout = 3, result_timeout = 30):
        if not query_name in self.registered_queries.keys():
            raise RuntimeError(f"Query: {query_name} is not registered in the list: {str(', ').join(self.registered_queries.keys())}")

        query = APIQueryInterruptible(compose_api_queries_pipe_names(self.fs_api_mount_directory, self.registered_queries[query_name], session_id))
        if len(session_id) != 0 and query_params.find("SESSION_ID=") == -1:
            if query_params == "0":
                query_params = f"SESSION_ID={session_id}"
            else:
                query_params += f"SESSION_ID={session_id}"
        status, timeout = query.execute(exec_timeout, query_params)
        if status == False or timeout <=0:
            raise RuntimeError(f"Cannot execute query: {query_name}, status: {status}, timeout: {timeout}")

        status, result, timeout = query.wait_result(result_timeout, session_id_value, 0.1, 30, True)
        if status == False or timeout <=0:
            raise RuntimeError(f"Couldn't get result for query: {query_name}, status: {status}, result: {result}, timeout: {timeout}")
        return status, result, timeout
