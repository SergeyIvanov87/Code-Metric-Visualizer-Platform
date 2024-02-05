#!/usr/bin/python

import os
import re
import stat

from math import log10

import filesystem_utils

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
    separated_completed_cmd_args = {}
    for arg_file_name in sorted(arg_names, key = first_index):
        with open(os.path.join(directory, arg_file_name),'rb') as thefile:
            arg_name = arg_file_name.split('.')[1]
            arg_value = thefile.read().decode('utf-8').strip()

            if arg_name in separated_args_names:
                if arg_name != "NO_NAME_PARAM":
                    separated_completed_cmd_args[arg_name] = ""
                if len(arg_value) > 0:
                    separated_completed_cmd_args[arg_name] = arg_value
                continue

            if arg_name != "NO_NAME_PARAM":
                completed_cmd_args.append(arg_name)
            if len(arg_value) > 0:
                 completed_cmd_args.append(arg_value)
    return completed_cmd_args, separated_completed_cmd_args

def read_args_dict(directory):
    files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    p = re.compile('[0-9]+\..*')
    arg_names = [ f for f in files if p.match(f) ]

    completed_cmd_args = {}
    for arg_file_name in sorted(arg_names, key = first_index):
        with open(os.path.join(directory, arg_file_name),'rb') as thefile:
            arg_name = arg_file_name.split('.')[1]
            arg_value = thefile.read().decode('utf-8')
            completed_cmd_args[arg_name] = arg_value.strip()
    return completed_cmd_args


def write_args(directory, rparams):
# create params as files
    counter = 0
    params_count = len(rparams)
    if params_count != 0:
        params_10based = int(log10(params_count)) + 1
        # put a leading zero as we need to get ordered params list
        param_digit_format = "{:0" + str(params_10based) + "d}"
        for param in rparams:
            param_name, param_value = param.split("=")
            param_name_filepath = os.path.join(directory, param_digit_format.format(counter) + "." + param_name)
            counter += 1

            with open(param_name_filepath, "w") as api_file_param:
                api_file_param.write(param_value)
                filesystem_utils.append_file_mode(
                    param_name_filepath,
                    stat.S_IWUSR
                    | stat.S_IRUSR
                    | stat.S_IWGRP
                    | stat.S_IRGRP
                    | stat.S_IWOTH
                    | stat.S_IROTH,
                )
