#!/usr/bin/python

import os
import pathlib
import pytest
import socket
import stat
import sys
import time

from settings import Settings
from utils import get_api_queries
from utils import compose_api_queries_pipe_names
from async_executor import AsyncExecutor

global_settings = Settings()
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())


class APIExecutor(AsyncExecutor):
    def __init__(self, api_mount_directory, query, index):
        AsyncExecutor.__init__(self)
        self.api_mount_directory = api_mount_directory
        self.query = query
        self.index = index
        self.error_message = ""

    @staticmethod
    def make_transaction(obj, number_of_transaction):
        session_id_value_base = socket.gethostname() + "_" + str(obj.index)
        for i in range(0, number_of_transaction):
            session_id_value = session_id_value_base + str(i)
            exec_params = "SESSION_ID=" + session_id_value

            # ask for a new pipe pairs every time once session id changed
            communication_pipes = compose_api_queries_pipe_names(
                obj.api_mount_directory, obj.query, session_id_value
            )

            # check API transaction
            print(
                f"API executor[{obj.index}], transaction: {i}",
                file=sys.stdout,
                flush=True,
            )
            with open(communication_pipes[0], "w") as pin:
                pin.write(exec_params + "\n")

            # wait for output pipe creation
            # wating timeout  might be increasedhere, because multiple threads
            # occupies more CPU time and a shceduler might supercede pipe creation server process
            api_result_pipe_timeout_cycles = 0
            api_result_pipe_timeout_cycles_limit = 100
            while not (
                os.path.exists(communication_pipes[1])
                and stat.S_ISFIFO(os.stat(communication_pipes[1]).st_mode)
            ):
                time.sleep(0.1)
                api_result_pipe_timeout_cycles += 1
                if (
                    api_result_pipe_timeout_cycles
                    >= api_result_pipe_timeout_cycles_limit
                ):
                    obj.error_message += f'ERROR: Output pipe "{communication_pipes[1]}" hasn\'t been created in designated interval {0.1 * float(api_result_pipe_timeout_cycles_limit)}sec'
                    break

            if len(obj.error_message):
                break

            with open(communication_pipes[1], "r") as pout:
                if not len(pout.read()):
                    obj.error_message += f'ERROR: Got empty result from the output pipe "{communication_pipes[1]}"'
                    break
                continue

            if len(obj.error_message):
                break

    def run(self, number_of_transaction=17):
        print(f"run API executor[{self.index}]", file=sys.stdout, flush=True)
        super().run(APIExecutor.make_transaction, [self, number_of_transaction])


@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes_multi_session(name, query, run_around_tests):
    global global_settings
    print(f"Test start: {name}", file=sys.stdout, flush=True)

    # compose expected pipe names, based on query data
    communication_pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)
    # check that special files are really pipes
    print(f"Check base API pipes: {communication_pipes}", file=sys.stdout, flush=True)
    for p in communication_pipes:
        api_result_pipe_timeout_cycles = 0
        while not (os.path.exists(p) and stat.S_ISFIFO(os.stat(p).st_mode)):
            time.sleep(0.1)
            api_result_pipe_timeout_cycles += 1
            assert api_result_pipe_timeout_cycles <= 30

    executors = []
    for i in range(0, os.cpu_count()):
        executor = APIExecutor(global_settings.api_dir, query, i)
        executor.run()
        executors.append(executor)

    for e in executors:
        e.join()

    for e in executors:
        assert e.error_message == "", "APIExecutor has no errors"
