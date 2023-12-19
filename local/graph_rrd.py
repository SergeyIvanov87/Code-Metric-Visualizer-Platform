#!/usr/bin/python

"""
The purpose of this module is to plot graphical data from hierarchical RRD databases
"""

import argparse
import csv
import os
import re
import subprocess
import sys

import read_api_fs_args

def get_last_timestamp(db_path, default_timestamp="1701154261"):
    timestamp=default_timestamp
    rrd_ask_result = subprocess.run(
                [
                    "rrdtool",
                    "last",
                    db_path,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                universal_newlines=True
            )
    if rrd_ask_result.returncode != 0:
        raise subprocess.CalledProcessError(rrd_ask_result.returncode, rrd_ask_result.args)
    if len(rrd_ask_result.stdout):
        timestamp = rrd_ask_result.stdout.split()[0]
    return timestamp

class RRDRecognizer:
    def __init__(self, leaf_regex="(.*::)*:[0-9]+\.rrd$"):
        self.leaf_pattern = re.compile(leaf_regex)

    def is_package(self, filepath):
        return os.path.isfile(filepath) and not self.leaf_pattern.match(filepath)

    def is_leaf(self, filepath):
        return os.path.isfile(filepath) and self.leaf_pattern.match(filepath)

def transform_counters_into_rrd_def(counters_list):
    abc_iter = iter(range(ord('a'),ord('z')+1))
    line_num = 1
    outputs = []
    for c in counters_list:
        line_name = chr(next(abc_iter))
        outputs.append(f"DEF:line{line_name}" + "={0}" + f":{c}:AVERAGE LINE{line_num}:line{line_name}#00FF00")
        line_num += 1
    return outputs

def graph_db_records(db_path, rrd_recognizer, graph_args, metrics_to_collect):
    filename = os.path.basename(db_path)
    dirname = os.path.dirname(db_path)
    output_graph_path = filename + ".img"
    graph_title = filename

    if rrd_recognizer.is_package(db_path):
        metric = metrics_to_collect[0].copy()
    elif rrd_recognizer.is_leaf(db_path):
        metric = metrics_to_collect[1].copy()
    else:
        raise Exception(f"Unrecognized RRD DB: {db_path}")

    formatted_metric=[]
    for m in metric:
        formatted_metric.append(m.format(db_path))

    rrd_update_result = subprocess.run(
        [
            "rrdtool",
            "graph",
            output_graph_path,
            *graph_args,
            *formatted_metric,
            "-t",
            graph_title
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    if len(rrd_update_result.stderr):
        print(f"Cannot build graph from DB records. {rrd_update_result.stderr}")

    if rrd_update_result.returncode != 0:
        raise subprocess.CalledProcessError(rrd_update_result.returncode, rrd_update_result.args)

    if len(rrd_update_result.stdout) != 1:
        raise Exception("Unexpected process output, requires one-liner result");
    return rrd_update_result.stdout.split('x')

def read_db_files_from_path(path, file_match_regex='.*\.rrd'):
    p = re.compile(file_match_regex)
    if os.path.isfile(path) and p.match(path):
        return [path]

    files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path,f))]
    rrd_db_files = [ os.path.join(path,f) for f in files if p.match(f) ]

    return rrd_db_files

parser = argparse.ArgumentParser(
    prog="RRD databases recursive graph plotter",
    description="Consumes components list as directories structure and fetch data from RRD in those directories"
)

parser.add_argument(
    "api_arg_dir"
)

args = parser.parse_args()

components_2_fetch = sys.stdin.read().split()
cmd_args_list, filtering_args_list = read_api_fs_args.read_n_separate_args(args.api_arg_dir, ["package_counters", "leaf_counters"])

rrd_files = []
for component in components_2_fetch:
    rrd_files.extend(read_db_files_from_path(component))

end_arg_index = cmd_args_list.index("-e")
end_arg_index += 1
end_arg_value = cmd_args_list[end_arg_index].lower()
if end_arg_value == "none" or end_arg_value == "" or end_arg_value == "last":
    if len(rrd_files) > 0:
        cmd_args_list[end_arg_index] = get_last_timestamp(rrd_files[0])

graph_counters_template = []
graph_counters_template.append(transform_counters_into_rrd_def(filtering_args_list["package_counters"].split(',')))
graph_counters_template.append(transform_counters_into_rrd_def(filtering_args_list["leaf_counters"].split(',')))
recognizer = RRDRecognizer()
for f in rrd_files:
    graph_db_records(f, recognizer, cmd_args_list, graph_counters_template)
