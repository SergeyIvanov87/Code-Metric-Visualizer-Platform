#!/usr/bin/python

import errno
import fcntl
import os
import stat
import sys
import time
import concurrent.futures
import threading

from queue import LifoQueue

def canonize_args(exec_args_str):
    canonized_exec_args_str = exec_args_str.strip().strip('\n')
    canonized_exec_args_str += '\n' # only one must survive
    return canonized_exec_args_str


class APIQuery:
    def __init__(self, command_pipes, remove_session_pipe_on_result_done = True):
        if len(command_pipes) < 2:
            raise RuntimeError(f"Cannot create APIQuery without at least 2 pipes, got: {command_pipes}");

        self.command_pipes = command_pipes
        self.remove_session_pipe_on_result_done = remove_session_pipe_on_result_done
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

    @staticmethod
    def __get_result_pipe__(command_pipes, session_id = ""):
        pipe_to_read = ""
        if session_id == "":
            pipe_to_read = APIQuery.__get_main_result_pipe__(command_pipes)
        else:
            for p in command_pipes:
                if p.endswith(session_id):
                    pipe_to_read = p
                    break

        if pipe_to_read == "":
            pipe_to_read = APIQuery.__get_main_result_pipe__(command_pipes) + "_" + session_id
        return pipe_to_read


    def is_valid(self, session_id=""):
        try:
            pipes = [APIQuery.__get_exec_pipe__(self.command_pipes), APIQuery.__get_result_pipe__(self.command_pipes, session_id)]
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
            if cycles_count >= max_cycles_count:
                break;

        return cycles_count <  max_cycles_count



    def execute(self, exec_args_str="0"):
        exec_pipe_path = APIQuery.__get_exec_pipe__(self.command_pipes)
        try:
            with open(exec_pipe_path, "w") as pin:
                pin.write(canonize_args(exec_args_str))
        except Exception as e:
            print(f"Query::execute failed on pipe '{exec_pipe_path}', while writing: {exec_args_str}. Exception: {e}", file=sys.stderr, flush=True)
            raise e

    def __wait_result_pipe_creation__(self, session_id, sleep_between_cycles, max_cycles_count, console_ping):
        cycles_count = 0
        pipe_to_read = APIQuery.__get_result_pipe__(self.command_pipes, session_id)
        while not (os.path.exists(pipe_to_read) and stat.S_ISFIFO(os.stat(pipe_to_read).st_mode)):
            time.sleep(sleep_between_cycles)
            cycles_count += 1

            if (cycles_count % 10) == 0 and console_ping:
                print(f"pipe '{pipe_to_read}' readiness awaiting is in progress[{cycles_count}]...", file=sys.stdout, flush=True)

            if cycles_count >= max_cycles_count:
                raise RuntimeError(f"Pipe: {pipe_to_read} - hasn't been created during expected timeout: sleep {sleep_between_cycles}, cycles {max_cycles_count}")
        return pipe_to_read

    def __wait_result_with_pipe_mode__(self, mode, session_id, sleep_between_cycles, max_cycles_count, console_ping):
        pipe_to_read = self.__wait_result_pipe_creation__(session_id, sleep_between_cycles, max_cycles_count, console_ping)

        with open(pipe_to_read, mode) as pout:
            result = pout.read()

        # TODO DO NOT remove temporal pipe even if it is not main session id
        #if self.remove_session_pipe_on_result_done:
        #    if session_id != "":
        #        os.remove(pipe_to_read)
        return result

    def wait_binary_result(self, session_id = "", sleep_between_cycles=0.1, max_cycles_count=30, console_ping = False):
        return self.__wait_result_with_pipe_mode__("rb", session_id, sleep_between_cycles, max_cycles_count, console_ping)

    def wait_result(self, session_id = "", sleep_between_cycles=0.1, max_cycles_count=30, console_ping = False):
        return self.__wait_result_with_pipe_mode__("r", session_id, sleep_between_cycles, max_cycles_count, console_ping)



def get_elapsed_duration(current_duration, begin_ts):
    end_ts = time.time()
    result = (current_duration - (end_ts - begin_ts)) if (current_duration > (end_ts - begin_ts)) else 0
    return float(result), end_ts

class APIQueryInterruptible(APIQuery):
    # TODO think about remove_session_pipe_on_result_done necessity.
    # It's must be clear that session pipes must be removed only by it's creator/owner
    # No one other must remove it.
    # I have to think about the question: do I realy need to remove them at all?
    def __init__(self, command_pipes, remove_session_pipe_on_result_done):
        super().__init__(command_pipes, remove_session_pipe_on_result_done)
        self.result_queue = LifoQueue()

    def __prepare_for_async__(self, wait_second_before_interrupt):
        begin_ts = time.time()  # measure duration

        # drain thread communication queues before proceed, to get off unread messages
        while not self.result_queue.empty():
            self.result_queue.get()

        # must not supply join() by 0 timeout not avoid be blocked forever
        if wait_second_before_interrupt <=0:
            wait_second_before_interrupt = 0.5
        return wait_second_before_interrupt, begin_ts

    def __finish_result_async__(self, wait_second_before_interrupt, begin_ts):
        # check if an exception happened
        wait_second_before_interrupt, end_ts = get_elapsed_duration(wait_second_before_interrupt, begin_ts)
        if self.result_queue.empty():
            return False, None, wait_second_before_interrupt
        return True, self.result_queue.get(), wait_second_before_interrupt

    def execute(self, wait_second_before_interrupt, exec_args_str="0"):
        wait_second_before_interrupt, local_begin_ts = self.__prepare_for_async__(wait_second_before_interrupt)

        relax_sleep_sec = 0.5
        exec_pipe_path = APIQuery.__get_exec_pipe__(self.command_pipes)
        pin = 0
        # the routine must ackomplish it job in a finite time
        # otherwise we will get a stall thread, waiting on pipe writing its data.
        # These parasitic writes can affect other consumers of pipes API by providing them an obsolete data

        # Here we must ensure that we will not block ourselves on an inactive pipe.
        # If the pipe is inactive that it means that a service, which is responsible for a given pipes API,
        # might delete a link on this pipe and recreate that pipe using a same name. But it will be a different pipe.
        # if it do that, this descriptor which we are waiting here for, will be inaccessible from the outside
        # and we cannot unblock it by reading its content using the name, because it will be the different pipe
        # So unblocking dealing with a descriptors here is an essential idea of this APIQueryInterruptible implementation
        while  wait_second_before_interrupt > 0:
            try:
                # we are trying to open a pipe here in nonblocking mode.
                # for success - the path of pipe must exist
                wait_second_before_interrupt, local_begin_ts = get_elapsed_duration(wait_second_before_interrupt, local_begin_ts)
                pin = os.open(exec_pipe_path,  os.O_NONBLOCK | os.O_WRONLY)
                break;
            except Exception as e:
                time.sleep(relax_sleep_sec)
                pass
        if wait_second_before_interrupt <= 0:
            return False, wait_second_before_interrupt
        # As we have successfully opened it without blocking,
        # then we no longer need to keep the handle as non-blocking
        flags = fcntl.fcntl(pin, fcntl.F_GETFL)
        flags &= ~os.O_NONBLOCK
        fcntl.fcntl(pin, fcntl.F_SETFL, flags)

        # the data to write in, must be terminated by \n
        data_to_write = canonize_args(exec_args_str)
        data_to_write_size=len(data_to_write)

        # pipe doesn't consume terminating \n here (for some reason), thus do not count it
        if data_to_write_size > 0 and data_to_write[-1] == '\n':
            data_to_write_size -= 1
        offset_to_write=0

        data_to_write = data_to_write.encode()
        try:
            while offset_to_write < data_to_write_size and wait_second_before_interrupt > 0:
                try:
                    # write until the end or timeout happened
                    wait_second_before_interrupt, local_begin_ts = get_elapsed_duration(wait_second_before_interrupt, local_begin_ts)
                    written=os.write(pin, data_to_write[offset_to_write:-1])
                    offset_to_write += written
                except OSError as err:
                    if err.errno != errno.EAGAIN and err.errno != errno.EWOULDBLOCK:
                        raise
                    time.sleep(relax_sleep_sec)
                except Exception as e:
                    time.sleep(relax_sleep_sec)
                    raise
        except Exception as e:
            pass
        finally:
            os.close(pin)

        # API is available if utter data portion has been written
        wait_second_before_interrupt, end_ts = get_elapsed_duration(wait_second_before_interrupt, local_begin_ts)
        return offset_to_write == data_to_write_size, wait_second_before_interrupt


    def __wait_result_with_pipe_mode_impl__(self, mode, session_id, sleep_between_cycles, max_cycles_count, console_ping, wait_second_before_interrupt, local_begin_ts):
        try:
            pipe_to_read = self.__wait_result_pipe_creation__(session_id, sleep_between_cycles, max_cycles_count, console_ping)
        except Exception as e:
            wait_second_before_interrupt, local_begin_ts = get_elapsed_duration(wait_second_before_interrupt, local_begin_ts)
            return False, None, wait_second_before_interrupt

        pin = 0
        # the thread must ackomplish it job in a finite time
        # otherwise we will get a stall thread, waiting on pipe reading its data.
        # These parasitic writes can affect other providers of pipes API by providing them an obsolete data

        # Here we must ensure that we will not block ourselves on an inactive pipe.
        # If the pipe is inactive that it means that a service, which is responsible for a given pipes API,
        # might delete a link on this pipe and recreate that pipe using a same name. But it will be a different pipe.
        # if it do that, this descriptor which we are waiting here for, will be inaccessible from the outside
        # and we cannot unblock it by writing its content using the name, because it will be the different pipe
        # So unblocking dealing with a descriptors here is an essential idea of this APIQueryInterruptible implementation
        while  wait_second_before_interrupt > 0:
            try:
                # we are trying to open a pipe here in nonblocking mode.
                # for success - the path of pipe must exist
                wait_second_before_interrupt, local_begin_ts = get_elapsed_duration(wait_second_before_interrupt, local_begin_ts)
                pin = os.open(pipe_to_read, os.O_NONBLOCK | os.O_RDONLY)
                break;
            except Exception as e:
                time.sleep(sleep_between_cycles)
                pass
        if wait_second_before_interrupt <= 0:
            # remove temporal pipe unless it's main session id
            if self.remove_session_pipe_on_result_done:
                if session_id != "":
                    os.remove(pipe_to_read)
            return

        read_data = ""
        read_data_size = 0
        total_read_data_size = 0
        try:
            while ((total_read_data_size <= 0 and read_data_size == 0) or read_data_size != 0) and wait_second_before_interrupt > 0:
                try:
                    # read until the end or timeout happened or something appear
                    wait_second_before_interrupt, local_begin_ts = get_elapsed_duration(wait_second_before_interrupt, local_begin_ts)
                    # TODO Need to think about adding ACTUAL DATA Size in pipe result
                    bytes_obj=os.read(pin, 4096000000)
                    read_data_size = len(bytes_obj)
                    total_read_data_size += read_data_size
                    read_data += bytes_obj.decode()
                    time.sleep(0.1)
                except OSError as err:
                    if err.errno != errno.EAGAIN and err.errno != errno.EWOULDBLOCK:
                        raise
                    time.sleep(sleep_between_cycles)
                except Exception as e:
                    time.sleep(sleep_between_cycles)
                    raise
        except Exception as e:
            pass
        finally:
            os.close(pin)

        # remove temporal pipe unless it's main session id
        if self.remove_session_pipe_on_result_done:
            if session_id != "":
                os.remove(pipe_to_read)

        # API is available if utter data portion has been read
        wait_second_before_interrupt, local_begin_ts = get_elapsed_duration(wait_second_before_interrupt, local_begin_ts)
        if total_read_data_size != 0:
            read_data = read_data.strip()
            self.result_queue.put(read_data)
            return True, read_data, wait_second_before_interrupt
        else:
            return False, None, wait_second_before_interrupt

    def wait_binary_result(self, wait_second_before_interrupt, session_id = "", sleep_between_cycles=0.1, max_cycles_count=30, console_ping = False):
        wait_second_before_interrupt, begin_ts = self.__prepare_for_async__(wait_second_before_interrupt)
        return self.__wait_result_with_pipe_mode_impl__("rb", session_id, sleep_between_cycles, max_cycles_count, console_ping, wait_second_before_interrupt, begin_ts)


    def wait_result(self, wait_second_before_interrupt, session_id = "", sleep_between_cycles=0.1, max_cycles_count=30, console_ping = False):
        wait_second_before_interrupt, begin_ts = self.__prepare_for_async__(wait_second_before_interrupt)
        return self.__wait_result_with_pipe_mode_impl__("r", session_id, sleep_between_cycles, max_cycles_count, console_ping, wait_second_before_interrupt, begin_ts)
