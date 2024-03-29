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
