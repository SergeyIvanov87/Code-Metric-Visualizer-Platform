#!/usr/bin/python

import os
import stat

def append_file_mode(file, append_modes):
    st = os.stat(file)
    os.chmod(file, st.st_mode | append_modes)

def append_file_list_mode(file_list, append_modes):
    for f in file_list:
        append_file_mode(f, append_modes)


def make_file_executable(file):
    append_file_mode(file, stat.S_IEXEC)
