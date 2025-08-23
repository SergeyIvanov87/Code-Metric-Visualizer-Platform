#!/usr/bin/python

"""
The purpose of this module is to generate hierarchical RRD databases
"""

import argparse
import json
import os
import subprocess
import stat
import sys

from argparse import RawTextHelpFormatter
from collections import defaultdict
from xml.etree.ElementTree import ElementTree, tostring
from xml.etree import ElementTree

import rrd_utils

sys.path.append('modules')
from filesystem_utils import append_file_mode

supported_methods = ["init", "update"]
xml_node_types = ["package", "file", "item"]

class rrd:
    def __init__(self, p_tree):
        self.packaged_tree = p_tree
        self.components_gathered = {t:0 for t in xml_node_types}

    def fill_data(self, rrd_db_file, single_timestamp, single_counters_list):
        record_str = single_timestamp + ":" + ":".join(single_counters_list)
        rrd_update_result = subprocess.run(
                [
                    "rrdtool",
                    "update",
                    rrd_db_file,
                    record_str
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
        if len(rrd_update_result.stderr):
            print(f"Cannot update DB. {rrd_update_result.stderr}")

        if rrd_update_result.returncode != 0:
            raise subprocess.CalledProcessError(rrd_update_result.returncode, rrd_update_result.args)

    @staticmethod
    def __extract_xml_node_name_type_id(xml_node):
        for node_type_index in range(0, len(xml_node_types)):
            item_name=xml_node.get(xml_node_types[node_type_index])
            if item_name is not None:
                item_name = rrd_utils.canonize_rrd_source_name(item_name)
                return item_name, node_type_index
        raise Exception(f"Unsupported node type in XML node {tostring(xml_node)}. Available types: {','.join(xml_node_types)}");

    @staticmethod
    def __extract_node_counter(xml_node):
        package_statistic = xml_node.findall("statistic")
        # means "package" or "file"
        if len(package_statistic) != 1:
            raise Exception(f"Expected node type: {','.join(xml_node_types[0,-2])}, must have only 1 'statistic` child.\nXML node{tostring(xml_node)}")
        attr_value = defaultdict(list)
        for elem in package_statistic[0]:
            value = elem.text[1:-1]
            name = elem.tag
            attr_value[name] =[v.strip() for v in value.split(",")]

        counters_snapshot = []
        counters_snapshot.extend(attr_value["mean"]);
        counters_snapshot.extend(attr_value["median"]);
        counters_snapshot.extend(attr_value["deviation"]);
        return counters_snapshot

    @staticmethod
    def __extract_leaf_counter(xml_node):
        # means "item"
        attr_value = defaultdict(list)
        for elem in xml_node:
            value = elem.text
            name = elem.tag
            attr_value[name]=value.strip()
        counters_snapshot = []
        counters_snapshot.append(attr_value["mmcc"]);
        counters_snapshot.append(attr_value["tmcc"]);
        counters_snapshot.append(attr_value["sif"]);
        counters_snapshot.append(attr_value["lif"]);
        counters_snapshot.extend(["nan"] * 8)
        return counters_snapshot

    def __build__(self, xml_package, args, path, timestamp, method):
        item_name, item_type_id=rrd.__extract_xml_node_name_type_id(xml_package)

        self.components_gathered[xml_node_types[item_type_id]] += 1

        statistic_node_name = os.path.join(path, item_name)
        statistic_node_db_name = f"{statistic_node_name}.rrd";
        need_to_fill = False
        # create RRD if not created
        # if it has been created at first time than fill it by initial data values
        if not os.path.isfile(statistic_node_db_name):
            need_to_fill = True
            rrd_create_result = subprocess.run(
                [
                    "rrdtool",
                    "create",
                    statistic_node_db_name,
                    *args
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            append_file_mode(statistic_node_db_name,
                             stat.S_IWUSR
                             | stat.S_IRUSR
                             | stat.S_IWGRP
                             | stat.S_IRGRP
                             | stat.S_IWOTH
                             | stat.S_IROTH
            )

        counters_snapshot = []
        if item_type_id in range(0,2):
            counters_snapshot = rrd.__extract_node_counter(xml_package)
        else:
            counters_snapshot = rrd.__extract_leaf_counter(xml_package)

        # update RRD if needed
        if method == "update" or need_to_fill == True:
            self.fill_data(statistic_node_db_name, timestamp, counters_snapshot)

        # go deep
        xml_child = xml_package.findall("entry")
        if len(xml_child) > 0:
            os.makedirs(statistic_node_name, mode=0o777, exist_ok=True)
        for c in xml_child:
            self.__build__(c, args, os.path.join(path, item_name), timestamp, method)


    def build(self, rrd_db_create_args, path, timestamp, method):
        xml = self.packaged_tree
        main_package = xml.findall("entry")
        if len(main_package) != 1:
            raise Exception(
                f"Only 1 main package `entry` element is expected in pmccabe xml"
            )
        # to create intermediate directories with a given permission
        # as os.makedirs() uses its mode argument only for a final directory
        cur_umask = os.umask(0) # umask is not the same as mode, 0 - means 777
        try:
            self.__build__(main_package[0], rrd_db_create_args, path, timestamp, method)
        except Exception as ex:
            raise
        finally:
            os.umask(cur_umask)

    def retrieve_last_ts(self, path):
        xml = self.packaged_tree
        main_package = xml.findall("entry")
        if len(main_package) != 1:
            raise Exception(
                f"Only 1 main package `entry` element is expected in pmccabe xml"
            )
        item_name, item_type_id=rrd.__extract_xml_node_name_type_id(main_package[0])
        if item_type_id != 0:
            raise Exception(f"main package `entry` must be '{xml_node_types[0]}' type")

        main_statistic_node_name = os.path.join(path, item_name)
        main_statistic_node_db_name = f"{main_statistic_node_name}.rrd";
        timestamp="1701154261"
        if not os.path.isfile(main_statistic_node_db_name):
            return timestamp
        else:
            rrd_ask_result = subprocess.run(
                [
                    "rrdtool",
                    "last",
                    main_statistic_node_db_name,
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


parser = argparse.ArgumentParser(
    formatter_class=RawTextHelpFormatter,
    prog="RRD databases tree builder",
    description="Consume output of `pmccabe` utility and build its tree representation for RRD databases"
)


parser.add_argument(
    "args"
)

parser.add_argument(
    "path"
)

parser.add_argument(
    "-method",
    "--method",
    default=supported_methods[1]
)

args = parser.parse_args()

pmccabe_tree_xml = sys.stdin.read()
return_data = { "error": -1, "statistic": {} }
try:
    xml_root = ElementTree.fromstring(pmccabe_tree_xml)

    processor = rrd(xml_root)
    timestamp=processor.retrieve_last_ts(args.path)
    timestamp = str(int(timestamp) + 1)
    processor.build(args.args.split(), args.path, timestamp, args.method)
    return_data["error"] = 0
    return_data["statistic"] = processor.components_gathered
except Exception as e:
    print(f"Build RRD failed with exception: {e}.\nPMCCabe XML:\n{pmccabe_tree_xml}")

print(json.dumps(return_data))
