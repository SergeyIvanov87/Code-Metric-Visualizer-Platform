#!/usr/bin/python

import console_server
import os
import pathlib
import pytest
import requests
import shutil
import stat
import sys
import time

from api_schema_utils import compose_api_queries_pipe_names
from api_schema_utils import deserialize_api_request_from_schema_file
from api_deps_utils import get_api_service_dependencies
from build_api_pseudo_fs import build_api_pseudo_fs
from services_utils import build_and_launch_services
from heartbeat import Heartbeat
from queries import FS_API_Executor
from settings import Settings
from time_utils import get_timestamp
from utils import get_api_queries
from utils import wait_until_pipe_exist

from build_common_api_services import build_ask_dependency_api_service
from build_common_api_services import make_script_unmet_dependencies

import api_fs_exec_utils
import api_fs_bash_utils

service_api_deps=dict()
service_unavailable_api_deps=dict()
global_settings = Settings()
global_depend_on_services_api_path = os.getenv('DEPEND_ON_SERVICES_API_SCHEMA_DIR', '')
inner_api_schema_path = os.getenv('INNER_API_SCHEMA_DIR', '')

service_api_deps = get_api_service_dependencies(global_depend_on_services_api_path, r".*", r".*\.json$")

global_depend_on_unreachable_services_api_path = os.getenv('DEPEND_ON_UNAVAILABLE_SERVICES_API_SCHEMA_DIR', '')
service_unavailable_api_deps = get_api_service_dependencies(global_depend_on_unreachable_services_api_path, r".*", r".*\.json$")


def stop_servers(servers):
    print("Stop console servers", file=sys.stdout, flush=True)
    # Tear down
    # stop servers
    for s in servers:
        console_server.kill_detached(s)

def remove_generated_files(files):
    for f in files:
        try:
            os.remove(f)
        except OSError:
            pass

def http_set_service_availability(http_node, service_name, available):
    url = f'http://{http_node}:80/set_service_availability'
    headers = {'Accept-Charset': 'UTF-8'}
    params = {"service_name":service_name, "available" :str(available)}
    resp = requests.get(url, params=params, headers=headers)
    assert resp.ok
    answer = str(resp.text)
    print(f"========Turning on {service_name} got answer: {answer}=======")
    assert answer.find("service_name") != -1
    return answer


@pytest.mark.parametrize("service_name,queries_map", service_api_deps.items())
def test_init_and_basic_functionality(service_name, queries_map):
    global global_settings
    global global_depend_on_services_api_path
    print(f"Test start: {service_name}", file=sys.stdout, flush=True)
    service_api_schemas_path=os.path.join(global_depend_on_services_api_path, service_name)

    # cleat FS
    shutil.rmtree(global_settings.api_dir, ignore_errors=True)
    generated_api_path = os.path.join(global_settings.work_dir, "generated")
    shutil.rmtree(generated_api_path, ignore_errors=True)
    os.mkdir(generated_api_path)

    # launch one particular stub service
    print(f"Launch server from schema: {service_api_schemas_path}")
    servers = build_and_launch_services(service_api_schemas_path, global_settings.work_dir, generated_api_path, global_settings.api_dir)

    # build & launch unmet_dependencies API
    print("Build pseudo-filesystem for inner API", file=sys.stdout, flush=True)
    build_api_pseudo_fs(inner_api_schema_path, global_settings.api_dir)

    generated_files_to_delete=[]
    unmet_dependencies_api_schema_file = os.path.join(inner_api_schema_path,"unmet_dependencies.json")
    unmet_dependencies_server_script_path, unmet_dependencies_exec_script_path = build_ask_dependency_api_service(unmet_dependencies_api_schema_file,
                                                                      os.path.join(global_settings.work_dir, "aux_services"),
                                                                      global_settings.work_dir, make_script_unmet_dependencies)
    generated_files_to_delete.extend([unmet_dependencies_server_script_path, unmet_dependencies_exec_script_path])

    unmet_dependencies_server_env = os.environ.copy()
    unmet_dependencies_server_env["WORK_DIR"] = global_settings.work_dir
    unmet_dependencies_server = console_server.launch_detached(unmet_dependencies_server_script_path, unmet_dependencies_server_env, "")
    print(f"Launched unmet_dependencies_server PID: {unmet_dependencies_server.pid}, PGID : {os.getpgid(unmet_dependencies_server.pid)}")
    servers.append(unmet_dependencies_server)


    # wait for output pipe creation, which means proxy has asked for unmet_dependencies and create its proxy services
    # otherwise  wait for PROXY pipes creations!!!!
    _, unmet_deps_request_data = deserialize_api_request_from_schema_file(unmet_dependencies_api_schema_file)
    unmet_deps_communication_pipes = compose_api_queries_pipe_names(global_settings.api_dir, unmet_deps_request_data)
    unmet_deps_communication_pipes_canonized=[]
    for p in unmet_deps_communication_pipes:
        if p.find("result.json") != -1:
            p = p + "_http_proxy_" + service_name + "_watchdog"
        unmet_deps_communication_pipes_canonized.append(p)

    # check that special files are really pipes
    print(f"Check base API pipes: {unmet_deps_communication_pipes_canonized}", file=sys.stdout, flush=True)
    got_unexpected_exception = False
    try:
        for p in unmet_deps_communication_pipes_canonized:
            wait_until_pipe_exist(p, 1, 30, True)
    except Exception as e:
        got_unexpected_exception = True

    if got_unexpected_exception:
        print(f"ERROR: Failed on waiting for unmet_dependencies result pipes creation: {unmet_deps_communication_pipes_canonized}")
        stop_servers(servers)
        remove_generated_files(generated_files_to_delete)
    assert not got_unexpected_exception



    # send queries to created service
    print(f"check self-created service: {service_name}")
    got_unexpected_exception = False
    try:
        executor = FS_API_Executor(service_api_schemas_path, global_settings.api_dir, global_settings.domain_name_api_entry)
        for query_name in queries_map.keys():
            out = executor.execute(query_name, f"TRACER_ID={query_name} SESSION_ID={service_name}", f"{service_name}")
            assert out
            assert out.startswith("echo args")
    except Exception as e:
        got_unexpected_exception = True

    if got_unexpected_exception:
        print(f"ERROR: Failed on testing unmet_dependencies service")
        stop_servers(servers)
        remove_generated_files(generated_files_to_delete)
    assert not got_unexpected_exception

    # check other services  which must have been proxied
    got_unexpected_exception = False
    for proxied_service, proxied_query_map in service_api_deps.items():
        if proxied_service == service_name:
            continue
        print(f"Check proxied service: {proxied_service}")
        proxied_service_api_schemas_path=os.path.join(global_depend_on_services_api_path, proxied_service)
        try:
            executor = FS_API_Executor(proxied_service_api_schemas_path, global_settings.api_dir, global_settings.domain_name_api_entry)
            for query_name in proxied_query_map.keys():
                print(f"check query name: {query_name}")
                assert executor.wait_until_valid(query_name, "", 1, 30, False), f"Proxied service: {proxied_service} must have been started"
                out = executor.execute(query_name, f"TRACER_ID={query_name} SESSION_ID={proxied_service}", f"{proxied_service}")
                print(f"proxied out: {out}")
                assert out
                assert out.startswith(global_settings.api_dir)
        except Exception as e:
            got_unexpected_exception = True
            print(f"Exception: {e}")

    if got_unexpected_exception:
        print(f"ERROR: Failed on testing proxied services")
        stop_servers(servers)
        remove_generated_files(generated_files_to_delete)
    assert not got_unexpected_exception



    print("Stop console servers", file=sys.stdout, flush=True)
    # Tear down
    # stop servers
    for s in servers:
        console_server.kill_detached(s)

    remove_generated_files(generated_files_to_delete)
    print(f"Test stop: {service_name}", file=sys.stdout, flush=True)
    assert not got_unexpected_exception


def make_script_unmet_dependencies_unreachable(script):
    file_extension = ".json"
    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_bash_utils.generate_extract_attr_value_from_string(), r"",
        *api_fs_bash_utils.generate_add_suffix_if_exist(), r"",
        *api_fs_bash_utils.generate_wait_until_pipe_exist(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        api_fs_bash_utils.extract_attr_value_from_string() + " \"SESSION_ID\" \"${2}\" \"\" '=' SESSION_ID_VALUE", r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${OVERRIDEN_CMD_ARGS[@]}" | xargs ${OPT_DIR}/check_missing_pseudo_fs_from_schema.py ${SHARED_API_DIR} "api.pmccabe_collector.restapi.org" ${DEPEND_ON_UNAVAILABLE_SERVICES_API_SCHEMA_DIR}',

    )
    script.writelines(line + "\n" for line in body)


@pytest.mark.parametrize("service_name,queries_map", service_unavailable_api_deps.items())
def test_unrechable_services(service_name, queries_map):
    global global_settings
    global global_depend_on_unreachable_services_api_path
    print(f"=========Test `test_unrechable_services` start: {service_name}==========", file=sys.stdout, flush=True)
    service_api_schemas_path=os.path.join(global_depend_on_unreachable_services_api_path, service_name)
    print(f"service_api_schemas_path: {service_api_schemas_path}")
    # cleat FS
    shutil.rmtree(global_settings.api_dir, ignore_errors=True)
    generated_api_path = os.path.join(global_settings.work_dir, "generated")
    shutil.rmtree(generated_api_path, ignore_errors=True)
    os.mkdir(generated_api_path)

    servers = []
    generated_files_to_delete = []

    # build & launch unmet_dependencies API
    print("===========Build pseudo-filesystem for inner API=========", file=sys.stdout, flush=True)
    build_api_pseudo_fs(inner_api_schema_path, global_settings.api_dir)

    unmet_dependencies_api_schema_file = os.path.join(inner_api_schema_path,"unmet_dependencies.json")
    unmet_dependencies_server_script_path, unmet_dependencies_exec_script_path = build_ask_dependency_api_service(unmet_dependencies_api_schema_file,
                                                                      os.path.join(global_settings.work_dir, "aux_services"),
                                                                      global_settings.work_dir, make_script_unmet_dependencies_unreachable)
    generated_files_to_delete.extend([unmet_dependencies_server_script_path, unmet_dependencies_exec_script_path])

    unmet_dependencies_server_env = os.environ.copy()
    unmet_dependencies_server_env["WORK_DIR"] = global_settings.work_dir
    unmet_dependencies_server = console_server.launch_detached(unmet_dependencies_server_script_path, unmet_dependencies_server_env, "")
    print(f"==============Launched unmet_dependencies_server PID: {unmet_dependencies_server.pid}, PGID : {os.getpgid(unmet_dependencies_server.pid)}=============")
    servers.append(unmet_dependencies_server)


    # wait for output pipe creation, which means proxy has asked for unmet_dependencies and create its proxy services
    # otherwise  wait for PROXY pipes creations!!!!
    _, unmet_deps_request_data = deserialize_api_request_from_schema_file(unmet_dependencies_api_schema_file)
    unmet_deps_communication_pipes = compose_api_queries_pipe_names(global_settings.api_dir, unmet_deps_request_data)
    unmet_deps_communication_pipes_canonized=[]
    for p in unmet_deps_communication_pipes:
        if p.find("result.json") != -1:
            p = p + "_http_proxy_" + service_name + "_watchdog"
        unmet_deps_communication_pipes_canonized.append(p)

    # check that special files are really pipes
    print(f"============Unreachable service must not ask base API pipes while its DOWNSTREAM_IS_DOWN: {unmet_deps_communication_pipes_canonized}=============", file=sys.stdout, flush=True)
    got_expected_exception = False
    try:
        for p in unmet_deps_communication_pipes_canonized:
            wait_until_pipe_exist(p, 1, 30, True)
    except Exception as e:
        got_expected_exception = True

    if not got_expected_exception:
        print(f"ERROR: Unreachable service got asked for unmet_dependencies result pipes creation: {unmet_deps_communication_pipes_canonized}. Even is DOWNSTREAM is dead=============")
        stop_servers(servers)
        remove_generated_files(generated_files_to_delete)
    assert  got_expected_exception

    ### Turn the DOWNSTREAM_SERVICE on
    downstream_service_url = os.getenv('DOWNSTREAM_SERVICE_NETWORK_ADDR', '')
    assert downstream_service_url != ''
    http_set_service_availability(downstream_service_url, service_name, True)

    print(f"======Unreachable service must became reachable und must ask for base API pipes: {unmet_deps_communication_pipes_canonized}==========", file=sys.stdout, flush=True)
    got_unexpected_exception = False
    try:
        for p in unmet_deps_communication_pipes_canonized:
            wait_until_pipe_exist(p, 1, 30, True)
    except Exception as e:
        got_unexpected_exception = True

    if got_unexpected_exception:
        print(f"ERROR: Failed on waiting for unmet_dependencies result pipes creation: {unmet_deps_communication_pipes_canonized}")
        stop_servers(servers)
        remove_generated_files(generated_files_to_delete)
        http_set_service_availability(downstream_service_url, service_name, False)
    assert not got_unexpected_exception


    # send queries to created service
    print(f"check self-created service: {service_name}")
    got_expected_exception = False
    got_error_response = False
    got_positive_answer=False

    executor = FS_API_Executor(service_api_schemas_path, global_settings.api_dir, global_settings.domain_name_api_entry)
    for query_name in queries_map.keys():
        try:
            print(f"======test query: {query_name}=======")
            assert executor.wait_until_valid(query_name,"", 1, 60, True)
            out = executor.execute(query_name, f"TRACER_ID={query_name} SESSION_ID={service_name}", f"{service_name}")
            print(f"=====proxied answer: {out}======")
            if query_name.find("not_available") != -1:
                if not out.startswith("echo args") and out.find("Page not found") != -1:
                    got_error_response=True
            else:
                if out.startswith(global_settings.api_dir):
                    got_positive_answer=True
        except Exception as e:
            got_expected_exception = True
            pass

    if not got_expected_exception and not got_error_response:
        print(f"ERROR: service {service_name} must have not respond" )
        stop_servers(servers)
        remove_generated_files(generated_files_to_delete)
        http_set_service_availability(downstream_service_url, service_name, False)
    assert (got_expected_exception or got_error_response)
    assert got_positive_answer, "One query must be positive"


    # Tear down
    stop_servers(servers)
    remove_generated_files(generated_files_to_delete)
    http_set_service_availability(downstream_service_url, service_name, False)

    # wait for proxy turns all services out as a part og tear down step
    # if we won't wait for it, that some proxy- fs API servers may be up after test finishes
    # and next time when a test clear api fs directory using shutil.rmtree
    # servers will be inoperable
    print(f"==============Wait for: {service_name} shutting down================", file=sys.stdout, flush=True)
    counter = 0
    services_are_available = True
    while services_are_available and counter < 60:
        services_are_available = False
        for query_name in queries_map.keys():
            try:
                services_are_available = (services_are_available or executor.wait_until_valid(query_name,"", 1, 60, True))
            except Exception as e:
                services_are_available = services_are_available or False
                pass
    assert not services_are_available, "Pipes responsible for FS API communication must be closed"

    print(f"==============Test stop: {service_name}================", file=sys.stdout, flush=True)
    assert not got_unexpected_exception


@pytest.mark.parametrize("service_name,queries_map", service_unavailable_api_deps.items())
def test_unreachable_queries_shutdown(service_name, queries_map):
    global global_settings
    global global_depend_on_unreachable_services_api_path
    print(f"Test `test_unreachable_queries_shutdown` start: {service_name}", file=sys.stdout, flush=True)
    service_api_schemas_path=os.path.join(global_depend_on_unreachable_services_api_path, service_name)
    print(f"service_api_schemas_path: {service_api_schemas_path}")

    # clear FS
    shutil.rmtree(global_settings.api_dir, ignore_errors=True)
    generated_api_path = os.path.join(global_settings.work_dir, "generated")
    shutil.rmtree(generated_api_path, ignore_errors=True)
    os.mkdir(generated_api_path)

    servers = []
    generated_files_to_delete = []

    # build & launch unmet_dependencies API
    print("Build pseudo-filesystem for inner API", file=sys.stdout, flush=True)
    build_api_pseudo_fs(inner_api_schema_path, global_settings.api_dir)

    unmet_dependencies_api_schema_file = os.path.join(inner_api_schema_path,"unmet_dependencies.json")
    unmet_dependencies_server_script_path, unmet_dependencies_exec_script_path = build_ask_dependency_api_service(unmet_dependencies_api_schema_file,
                                                                      os.path.join(global_settings.work_dir, "aux_services"),
                                                                      global_settings.work_dir, make_script_unmet_dependencies_unreachable)
    generated_files_to_delete.extend([unmet_dependencies_server_script_path, unmet_dependencies_exec_script_path])

    unmet_dependencies_server_env = os.environ.copy()
    unmet_dependencies_server_env["WORK_DIR"] = global_settings.work_dir
    unmet_dependencies_server = console_server.launch_detached(unmet_dependencies_server_script_path, unmet_dependencies_server_env, "")
    print(f"Launched unmet_dependencies_server PID: {unmet_dependencies_server.pid}, PGID : {os.getpgid(unmet_dependencies_server.pid)}")
    servers.append(unmet_dependencies_server)


    ### Turn the DOWNSTREAM_SERVICE on
    downstream_service_url = os.getenv('DOWNSTREAM_SERVICE_NETWORK_ADDR', '')
    assert downstream_service_url != ''
    http_set_service_availability(downstream_service_url, service_name, True)

    # send queries to created service
    print(f"check self-created service, which must respond: {service_name}")
    got_expected_exception = False
    got_error_response = False
    got_positive_answer=False

    executor = FS_API_Executor(service_api_schemas_path, global_settings.api_dir, global_settings.domain_name_api_entry)
    for query_name in queries_map.keys():
        try:
            print(f"test query: {query_name}")
            assert executor.wait_until_valid(query_name,"", 1, 120, True)
            out = executor.execute(query_name, f"TRACER_ID={query_name} SESSION_ID={service_name}", f"{service_name}")
            print(f"proxied answer: {out}")
            if query_name.find("not_available") != -1:
                if not out.startswith("echo args") and out.find("Page not found") != -1:
                    got_error_response=True
            else:
                if out.startswith(global_settings.api_dir):
                    got_positive_answer=True
        except Exception as e:
            got_expected_exception = True
            pass

    if not got_expected_exception and not got_error_response:
        print(f"ERROR: service {service_name} must have not respond" )
        stop_servers(servers)
        remove_generated_files(generated_files_to_delete)
        http_set_service_availability(downstream_service_url, service_name, False)
    assert (got_expected_exception or got_error_response)
    assert got_positive_answer, "One query must be positive"

    print(f"==================Shutdown downstream service==================")
    h = Heartbeat()
    h.run(f"{get_timestamp()}\tTest 'turn down service: {service_name}' is in progress...")
    http_set_service_availability(downstream_service_url, service_name, False)
    time.sleep(30)
    h.stop()

    print(f"==================check self-created service, which must NOT response: {service_name}==================")
    got_expected_exception = False
    got_positive_answer=False

    for query_name in queries_map.keys():
        try:
            print(f"test query: {query_name}")
            executor.wait_until_valid(query_name,"", 1, 3, True)
            out = executor.execute(query_name, f"TRACER_ID={query_name} SESSION_ID={service_name}", f"{service_name}")
            assert out
            got_positive_answer = True
        except Exception as e:
            got_expected_exception = True
            pass

    if not got_expected_exception or got_positive_answer:
        print(f"ERROR: service {service_name} must have not respond" )
        stop_servers(servers)
        remove_generated_files(generated_files_to_delete)
        http_set_service_availability(downstream_service_url, service_name, False)

    # Tear down
    stop_servers(servers)
    remove_generated_files(generated_files_to_delete)
    http_set_service_availability(downstream_service_url, service_name, False)

    print(f"Test stop: {service_name}", file=sys.stdout, flush=True)
