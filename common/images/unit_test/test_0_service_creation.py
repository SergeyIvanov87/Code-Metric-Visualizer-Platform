#!/usr/bin/python

import os
import pathlib
import pytest
import stat
import shutil
import socket
import sys
import time

import console_server

from settings import Settings
from utils import get_api_queries
from utils import compose_api_queries_pipe_names
from build_api_executors import build_api_executors
from build_api_services import build_api_services
from build_api_pseudo_fs import build_api_pseudo_fs
from async_executor import AsyncExecutor

global_settings = Settings()
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())

@pytest.fixture(scope='function', autouse=True)
def run_around_tests():
    # Tear up
    global global_settings

    generated_api_rel_path = "generated"
    generated_api_path = os.path.join(global_settings.work_dir, generated_api_rel_path)
    shutil.rmtree(generated_api_path, ignore_errors=True)
    os.mkdir(generated_api_path)

    build_api_executors("/API", global_settings.work_dir, generated_api_path)

    generated_api_services_rel_path = "services"
    generated_api_services_path = os.path.join(generated_api_path, generated_api_services_rel_path)
    build_api_services("/API", generated_api_path, generated_api_services_path)
    server_scripts = [os.path.join(generated_api_services_path, f) for f in  os.listdir(generated_api_services_path)]
    assert len(server_scripts)

    print("Build pseudo-filesystem API", file=sys.stdout, flush=True)
    generated_api_mount_point = global_settings.api_dir
    shutil.rmtree(generated_api_mount_point, ignore_errors=True)
    build_api_pseudo_fs("/API", generated_api_mount_point)

    print("Launch servers", file=sys.stdout, flush=True)
    server_env = os.environ.copy()
    server_env["WORK_DIR"] = generated_api_path
    servers=[]
    for s in server_scripts:
        servers.append(console_server.launch_detached(s, server_env, ""))

    print("yield", file=sys.stdout, flush=True)
    yield servers
    print("Tear down", file=sys.stdout, flush=True)
    # Tear down
    # stop servers
    for s in servers:
        console_server.kill_detached(s)

    # avoid zombies
    print("avoid zombies", file=sys.stdout, flush=True)
    for s in servers:
        s.wait(timeout=3)


@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes_main_session(name, query, run_around_tests):
    global global_settings
    print(f"Test start: {name}", file=sys.stdout, flush=True)

    # compose expected pipe names, based on query data
    communication_pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)

    # check that special files are really pipes
    print(f"Check API pipes: {communication_pipes}", file=sys.stdout, flush=True)
    for p in communication_pipes:
        api_result_pipe_timeout_cycles=0
        while not (os.path.exists(p) and stat.S_ISFIFO(os.stat(p).st_mode)):
            time.sleep(0.1)
            api_result_pipe_timeout_cycles += 1
            assert api_result_pipe_timeout_cycles <= 30

    # check API transaction
    print(f"Check API transaction: {name}", file=sys.stdout, flush=True)
    with open(communication_pipes[0], "w") as pin:
        pin.write("0")
    with open(communication_pipes[1], "r") as pout:
        out = pout.read()
        print(f"Transaction result: {out}", file=sys.stdout, flush=True)
        assert len(out)
        return
    assert 0

'''
class APIExecutor(AsyncExecutor):
    def __init__(self, communication_pipes, index):
        super.__init(self)
        self.communication_pipes = communication_pipes
        self.index = index

    def make_transaction(self, number_of_transaction):
        session_id_value = socket.gethostname() + "_" + str(self.index)
        for i in range(0, number_of_transaction):
            exec_params = "SESSION_ID=" + session_id_value + str(i)

            # check API transaction
            print(f"API executor[{self.index}], transaction: {i}", file=sys.stdout, flush=True)
            with open(self.communication_pipes[0], "w") as pin:
                pin.write(exec_params)
            with open(self.communication_pipes[1], "r") as pout:
                assert len(pout.read())
            assert 0

    def run(self, number_of_transaction = 17):
        print(f"run API executor[{self.index}]", file=sys.stdout, flush=True)
        super.run(self, self.make_transaction, self, number_of_transaction)


@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes_multi_session(name, query, run_around_tests):
    global global_settings
    print(f"Test start: {name}", file=sys.stdout, flush=True)

    # compose expected pipe names, based on query data
    communication_pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)
    # check that special files are really pipes
    print(f"Check API pipes: {communication_pipes}", file=sys.stdout, flush=True)
    for p in communication_pipes:
        assert os.path.exists(p)
        assert stat.S_ISFIFO(os.stat(p).st_mode)


    # compose expected pipe names, based on query data
    session_id_value = socket.gethostname() + "_" + name
    exec_params = "SESSION_ID=" + session_id_value

    executors=[]
    for i in range(0,1):
        executor = APIExecutor(communication_pipes, i);
        executor.run()
        executors.append(executor)

    for e in executors:
        e.join()
'''
