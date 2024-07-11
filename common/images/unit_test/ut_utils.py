#!/usr/bin/python

import filesystem_utils
import os
import socket
import sys

from subprocess import check_output
from async_executor import AsyncExecutor
from utils import compose_api_queries_pipe_names

from api_fs_query import APIQuery

def create_executable_file(path_nodes_list, filename, lines_to_write):
    executable_filepath = os.path.join(*path_nodes_list, filename)
    with open(executable_filepath, "w") as executable_file:
        executable_file.writelines(lines_to_write)
    filesystem_utils.make_file_executable(executable_filepath)


def get_pids(name):
    return map(int,check_output(["pidof",name]).split())

class APIExecutor(AsyncExecutor):
    def __init__(self, api_mount_directory, query, index, onTransactionAdditionalInit = None, onPreExecute = None, onPostExecute = None, onPostWaitResultSuccess = None, onPostWaitResultFailed = None):
        AsyncExecutor.__init__(self)
        self.api_mount_directory = api_mount_directory
        self.query = query
        self.index = index
        self.error_message = "<the text must be overwritten unless query fails>"

        self.onTransactionAdditionalInit = onTransactionAdditionalInit
        self.onPreExecute = onPreExecute
        self.onPostExecute = onPostExecute
        self.onPostWaitResultSuccess = onPostWaitResultSuccess
        self.onPostWaitResultFailed = onPostWaitResultFailed

    def onTransaction(self, transcation_id):
        print(f"APIExecutor[{self.index}].onTransaction: {transcation_id}", file=sys.stdout, flush=True)
        session_id_value_base = socket.gethostname() + "_" + str(self.index)
        session_id_value = session_id_value_base + str(transcation_id)
        exec_params = "SESSION_ID=" + session_id_value
        if self.onTransactionAdditionalInit:
            return (session_id_value, exec_params, self.onTransactionAdditionalInit(self, exec_params))
        else:
            return (session_id_value, exec_params, [])

    @staticmethod
    def make_transaction(obj, number_of_transaction):
        for i in range(0, number_of_transaction):
            (session_id_value, exec_params, additional_params) = obj.onTransaction(i)

            # ask for a new pipe pairs every time once session id changed
            query = APIQuery(compose_api_queries_pipe_names(
                obj.api_mount_directory, obj.query, session_id_value
            ))
            assert query.wait_until_valid(0.1, 30, True), f"Pipes for test {name} must have been created"

            # check API transaction
            print(
                f"APIExecutor[{obj.index}], transaction: {i}",
                file=sys.stdout,
                flush=True,
            )

            if obj.onPreExecute :
                exec_params = obj.onPreExecute(obj, exec_params, additional_params)
            print(f"APIExecutor[{obj.index}] is about to write: {exec_params}", file=sys.stdout, flush=True)
            query.execute(exec_params)
            if obj.onPostExecute :
                obj.onPostExecute(obj, exec_params, additional_params)
            # wait for output pipe creation
            # wating timeout  might be increased here, because multiple threads
            # occupies more CPU time and a scheduler might supercede a pipe creation server process errand
            # by other activity
            result = ""
            try:
                result = query.wait_result(session_id_value, 0.1, 100, True)
                obj.error_message=""
            except RuntimeError as timeout:
                if obj.onPostWaitResultFailed :
                    obj.onPostWaitResultFailed(obj, exec_params, additional_params, result)

                obj.error_message += f'ERROR: Response pipe for session "{session_id_value}" hasn\'t been created in designated interval {0.1 * float(100)}sec'

            if obj.onPostWaitResultSuccess :
                obj.onPostWaitResultSuccess(obj, exec_params, additional_params, result)

            if result == "":
                obj.error_message += f'ERROR: Got empty result from the session "{session_id_value}"'

            if len(obj.error_message):
                break

    def run(self, number_of_transaction=17):
        print(f"run APIExecutor[{self.index}]", file=sys.stdout, flush=True)
        super().run(APIExecutor.make_transaction, [self, number_of_transaction])
