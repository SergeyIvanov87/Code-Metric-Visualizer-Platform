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

from collections import defaultdict
from math import sqrt

import rrd_utils
sys.path.append('modules')

import api_fs_args
import filesystem_utils

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

def translate_counter_name(name):
    translation_map = {"mmcc_mean" : "mmcc", "tmcc_mean" : "tmcc", "sif_mean" : "sif", "lif_mean" : "lif"}
    if name in translation_map.keys():
        return translation_map[name]
    return name

def transform_counters_into_rrd_def(counters_color_list):
    abc_iter = iter(range(ord('a'),ord('z')+1))
    line_num = 1
    outputs = []
    for cc_pair in counters_color_list:
        line_name = chr(next(abc_iter))
        counter, colour = cc_pair.split(':')
        counter = translate_counter_name(counter)
        outputs.append(f"DEF:line{line_name}" + "={0}" + f":{counter}:AVERAGE LINE{line_num}:line{line_name}#{colour}")
        line_num += 1
    return outputs

def graph_db_records(db_path, rrd_recognizer, graph_args, metrics_to_collect):
    filename = os.path.basename(db_path)
    dirname = os.path.dirname(db_path)

    # extract format and form file extension based on that
    graph_ext = graph_args[graph_args.index("-a") + 1].lower()

    output_graph_path = os.path.join(dirname,filename + "." + graph_ext)
    source_name = os.path.splitext(filename)[0]
    graph_title = rrd_utils.decanonize_rrd_source_name(source_name)

    # ask for a proper metrics depending on DB type
    if rrd_recognizer.is_package(db_path):
        metric = metrics_to_collect[0].copy()
    elif rrd_recognizer.is_leaf(db_path):
        metric = metrics_to_collect[1].copy()
    else:
        raise Exception(f"Unrecognized RRD DB: {db_path}")


    formatted_metric=[]
    for m in metric:
        formatted_metric.extend(m.format(db_path).split())

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

    return output_graph_path, rrd_update_result.stdout.split('x')

def read_db_files_from_path(path, file_match_regex='.*\.rrd$'):
    return filesystem_utils.read_files_from_path(path, '.*\.rrd$')

parser = argparse.ArgumentParser(
    prog="RRD databases recursive graph plotter",
    description="Consumes components list as directories structure and fetch data from RRD in those directories"
)

parser.add_argument(
    "api_arg_dir"
)

parser.add_argument(
    "output"
)
args = parser.parse_args()

components_2_fetch = sys.stdin.read().split()
cmd_args_list, filtering_args_list = api_fs_args.read_n_separate_args(args.api_arg_dir, ["package_counters", "leaf_counters", "colors"])

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

plotted_graphs_wit_res = defaultdict(list)
for f in rrd_files:
    plot_path, resolution = graph_db_records(f, recognizer, cmd_args_list, graph_counters_template)
    plotted_graphs_wit_res[plot_path] = resolution

# unify images into single one
grid_row = int(sqrt(len(plotted_graphs_wit_res)))
grid_column = int(len(plotted_graphs_wit_res) / grid_row)

image_montage_result = subprocess.run(
        [
            "magick",
            "montage",
            *plotted_graphs_wit_res.keys(),
            "-geometry",
            f"+{grid_row}+{grid_column}",
            args.output+".png"
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

if len(image_montage_result.stderr):
    print(f"Cannot build graph from DB records. {image_montage_result.stderr}")

if image_montage_result.returncode != 0:
    raise subprocess.CalledProcessError(image_montage_result.returncode, image_montage_result.args)
