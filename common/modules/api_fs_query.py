#!/usr/bin/python

import os
import stat
import sys
import time

def canonize_args(exec_args_str):
    canonized_exec_args_str = exec_args_str.strip().strip('\n')
    canonized_exec_args_str += '\n' # only one must survive
    return canonized_exec_args_str


class APIQuery:
    def __init__(self, command_pipes):
        if len(command_pipes) < 2:
            raise RuntimeError(f"Cannot create APIQuery without at least 2 pipes, got: {command_pipes}");

        self.command_pipes = command_pipes
        APIQuery.__get_exec_pipe__(self.command_pipes)
        APIQuery.__get_main_result_pipe__(self.command_pipes)

    @staticmethod
    def __get_exec_pipe__(command_pipes):
        major_pipe_names = "exec"
        pipe=""
        for p in command_pipes:
            if p.endswith(major_pipe_names):
                return p
        raise RuntimeError(f"APIQuery must comprise \"{major_pipe_names}\" pipe, got {command_pipes}");

    @staticmethod
    def __get_main_result_pipe__(command_pipes):
        major_pipe_name = "result"
        min_length_ext_pipe = ""
        min_length_ext_size = sys.maxsize
        min_length_name_size = sys.maxsize
        for p in command_pipes:
            name, ext = os.path.splitext(os.path.basename(p))
            if name.find(major_pipe_name) != -1:
                if len(ext) <= min_length_ext_size and len(name) <= min_length_name_size:
                    min_length_ext_size = len(ext)
                    min_length_name_size = len(name)
                    min_length_ext_pipe = p
        if min_length_ext_pipe == "":
            raise RuntimeError(f"APIQuery must comprise \"{major_pipe_name}\" pipe, got {command_pipes}");
        return os.path.join(os.path.dirname(min_length_ext_pipe), os.path.basename(min_length_ext_pipe).split('_')[0]) # if we have no pure main result pipe, mean it!

    def is_valid(self):
        try:
            pipes = [APIQuery.__get_exec_pipe__(self.command_pipes), APIQuery.__get_main_result_pipe__(self.command_pipes)]
            for p in pipes:
                if not (os.path.exists(p) and stat.S_ISFIFO(os.stat(p).st_mode)):
                    return False
        except Exception as e:
            raise e
        return True

    def wait_until_valid(self, sleep_between_cycles=0.1, max_cycles_count=30, console_ping = False):
        cycles_count = 0
        while not self.is_valid():
            time.sleep(sleep_between_cycles)
            cycles_count += 1

            if (cycles_count % 10) == 0 and console_ping:
                print(f"pipes '{self.command_pipes}' readiness awaiting is in progress[{cycles_count}]...", file=sys.stdout, flush=True)

        return cycles_count <  max_cycles_count



    def execute(self, exec_args_str="0"):
        exec_pipe_path = APIQuery.__get_exec_pipe__(self.command_pipes)
        with open(exec_pipe_path, "w") as pin:
            pin.write(canonize_args(exec_args_str))

    def __wait_result_with_pipe_mode__(self, mode, session_id, sleep_between_cycles, max_cycles_count, console_ping):
        cycles_count = 0
        pipe_to_read = ""
        if session_id == "":
            pipe_to_read = APIQuery.__get_main_result_pipe__(self.command_pipes)
        else:
            for p in self.command_pipes:
                if p.endswith(session_id):
                    pipe_to_read = p
                    break

        if pipe_to_read == "":
            pipe_to_read = APIQuery.__get_main_result_pipe__(self.command_pipes) + "_" + session_id

        while not (os.path.exists(pipe_to_read) and stat.S_ISFIFO(os.stat(pipe_to_read).st_mode)):
            time.sleep(sleep_between_cycles)
            cycles_count += 1

            if (cycles_count % 10) == 0 and console_ping:
                print(f"pipe '{pipe_to_read}' readiness awaiting is in progress[{cycles_count}]...", file=sys.stdout, flush=True)

            if cycles_count >= max_cycles_count:
                raise RuntimeError(f"Pipe: {pipe_to_read} - hasn't been created during expected timeout: sleep {sleep_between_cycles}, cycles {max_cycles_count}")

        with open(pipe_to_read, mode) as pout:
            result = pout.read()

        # remove temporal pipe unless it's main session id
        if session_id != "":
            os.remove(pipe_to_read)
        return result

    def wait_binary_result(self, session_id = "", sleep_between_cycles=0.1, max_cycles_count=30, console_ping = False):
        return self.__wait_result_with_pipe_mode__("rb", session_id, sleep_between_cycles, max_cycles_count, console_ping)

    def wait_result(self, session_id = "", sleep_between_cycles=0.1, max_cycles_count=30, console_ping = False):
        return self.__wait_result_with_pipe_mode__("r", session_id, sleep_between_cycles, max_cycles_count, console_ping)
