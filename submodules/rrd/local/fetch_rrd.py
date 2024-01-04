#!/usr/bin/python

"""
The purpose of this module is to fetch data from hierarchical RRD databases
"""

import argparse
import csv
import os
import re
import subprocess
import sys

sys.path.append(os.environ['MAIN_IMAGE_ENV_SHARED_LOCATION_ENV'])
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

def fetch_db_records(db_path, fetch_args):
    rrd_update_result = subprocess.run(
        [
            "rrdtool",
            "fetch",
            db_path,
            *fetch_args
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    if len(rrd_update_result.stderr):
        print(f"Cannot fetch DB records. {rrd_update_result.stderr}")

    if rrd_update_result.returncode != 0:
        raise subprocess.CalledProcessError(rrd_update_result.returncode, rrd_update_result.args)

    if len(rrd_update_result.stdout) < 2:
        raise Exception("Unexpected process output, requires 2 record lines at least");

    stdout_lines = rrd_update_result.stdout.split('\n')
    head = list(db_path + "/" + h for h in stdout_lines[0].split())
    line_size = 0;
    body =[]
    for l in stdout_lines[1:-1]:
        if len(l)==0:
            continue
        splitted_line = list(v.strip(' :') for v in l.split() if len(v) > 0)
        body.append(splitted_line)
        line_size = len(splitted_line)

    # first row with headers is shorter than data row,thus insert missed field descriptor
    if len(head) == line_size - 1:
        head.insert(0, "TIME")
    return head, body


def read_db_files_from_path(path, file_match_regex='.*\.rrd$'):
    p = re.compile(file_match_regex)
    if os.path.isfile(path) and p.match(path):
        return [path]

    files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path,f))]
    rrd_db_files = [ os.path.join(path,f) for f in files if p.match(f) ]

    return rrd_db_files

parser = argparse.ArgumentParser(
    prog="RRD databases recursive fetcher",
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

aggregated_body = []
aggregated_head = []


end_arg_index = cmd_args_list.index("-e")
end_arg_index += 1
end_arg_value = cmd_args_list[end_arg_index].lower()
if end_arg_value == "none" or end_arg_value == "" or end_arg_value == "last":
    if len(rrd_files) > 0:
        cmd_args_list[end_arg_index] = get_last_timestamp(rrd_files[0])

index = 0
for f in rrd_files:
    h, b = fetch_db_records(f, cmd_args_list)

    if index == 0:
        aggregated_head.extend(h)
        aggregated_body.extend(b)
    else:
        aggregated_head.extend(h[1:-1]) #remove TIME
        body_iter = iter(b)
        for aggregated_body_row in aggregated_body:
            aggregated_body_row.extend(next(body_iter)[1:-1])   # remove TIME value
    index += 1

# write to stddout to use redirection later
writer = csv.writer(sys.stdout)
writer.writerow(aggregated_head)
writer.writerows(aggregated_body)
