#!/usr/bin/python

import os
import re

def first_index(x):
    return x.split('.')[0]

def read_args(directory):
    files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    p = re.compile('[0-9]+\..*')
    arg_names = [ f for f in files if p.match(f) ]

    completed_cmd_args = []
    for arg_file_name in sorted(arg_names, key = first_index):
        with open(os.path.join(directory, arg_file_name),'rb') as thefile:
            arg_name = arg_file_name.split('.')[1]
            arg_value = thefile.read().decode('utf-8')
            if arg_name != "NO_NAME_PARAM":
                completed_cmd_args.append(arg_name)
            if len(arg_value) > 0:
                 completed_cmd_args.append(arg_value.strip())
    return completed_cmd_args

def read_n_separate_args(directory, separated_args_names=[]):
    files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    p = re.compile('[0-9]+\..*')
    arg_names = [ f for f in files if p.match(f) ]

    completed_cmd_args = []
    separated_completed_cmd_args = []
    for arg_file_name in sorted(arg_names, key = first_index):
        with open(os.path.join(directory, arg_file_name),'rb') as thefile:
            arg_name = arg_file_name.split('.')[1]
            arg_value = thefile.read().decode('utf-8').strip()

            if arg_value in separated_args_names:
                if arg_name != "NO_NAME_PARAM":
                    separated_completed_cmd_args.append(arg_name)
                if len(arg_value) > 0:
                    separated_completed_cmd_args.append(arg_value)
                continue

            if arg_name != "NO_NAME_PARAM":
                completed_cmd_args.append(arg_name)
            if len(arg_value) > 0:
                 completed_cmd_args.append(arg_value)
    return completed_cmd_args, separated_completed_cmd_args
