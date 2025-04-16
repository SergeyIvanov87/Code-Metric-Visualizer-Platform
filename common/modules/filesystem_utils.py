#!/usr/bin/python

import os
import re
import stat

def append_file_mode(file, append_modes):
    st = os.stat(file)
    os.chmod(file, st.st_mode | append_modes)

def append_file_list_mode(file_list, append_modes):
    for f in file_list:
        append_file_mode(f, append_modes)


def make_file_executable(file):
    append_file_mode(file, stat.S_IEXEC)

def read_files_from_path(path, file_match_regex):
    p = re.compile(file_match_regex)
    if os.path.isfile(path) and p.match(path):
        return [path]

    files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path,f))]
    matched_files = [ os.path.join(path,f) for f in files if p.match(f) ]

    return matched_files


def read_pipes_from_path(path, pipe_match_regex):
    p = re.compile(pipe_match_regex)
    if os.path.isfile(path) and stat.S_ISFIFO(os.stat(path).st_mode) and p.match(path):
        return [path]

    matched_pipes=[]

    # os.listdir throws sometimes
    try:
        pipes = [f for f in os.listdir(path) if stat.S_ISFIFO(os.stat(os.path.join(path,f)).st_mode)]
        matched_pipes = [ os.path.join(path,f) for f in pipes if p.match(f) ]
    except Exception as e:
        pass

    return matched_pipes


def create_executable_file(path_nodes_list, filename, lines_to_write):
    executable_filepath = os.path.join(*path_nodes_list, filename)
    with open(executable_filepath, "w") as executable_file:
        executable_file.writelines(lines_to_write)
    make_file_executable(executable_filepath)
