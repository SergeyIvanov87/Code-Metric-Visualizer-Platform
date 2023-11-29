#!/usr/bin/python

"""
The purpose of this module is to generate hierarchical RRD databases
"""

import argparse
import os
import subprocess
import sys

from argparse import RawTextHelpFormatter
from collections import defaultdict
from xml.etree.ElementTree import ElementTree
from xml.etree import ElementTree

#sys.path.insert(1, 'pmccabe_visualizer')
#import package_tree

supported_methods = ["init", "update"]

class rrd:
    def __init__(self, p_tree):
        self.packaged_tree = p_tree

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
        for stdout_line in rrd_update_result.stderr:
            print( stdout_line )
        if rrd_update_result.returncode != 0:
            raise subprocess.CalledProcessError(rrd_update_result.returncode, rrd_update_result.args)

    def __build__(self, xml_package, args, path, timestamp, method):
        item_name=xml_package.get("package")
        if item_name is None:
            item_name=xml_package.get("file")
        if item_name is None:
            item_name=xml_package.get("item")

        db_name = os.path.join(path, item_name)
        filename = f"{db_name}.rrd";
        need_to_fill = False
        # create RRD if not created
        # if it has been created at first time than fill it by initial data values
        if not os.path.isfile(filename):
            need_to_fill = True
            rrd_create_result = subprocess.run(
                [
                    "rrdtool",
                    "create",
                    filename,
                    *args
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )


        package_statistic = xml_package.findall("statistic")
        # means "package" or "file"
        if len(package_statistic) == 1:
            attr_value = defaultdict(list)
            for elem in package_statistic[0]:
                value = elem.text[1:-1]
                name = elem.tag
                attr_value[name] =[v.strip() for v in value.split(",")]

            counters_snapshot = []
            counters_snapshot.extend(attr_value["mean"]);
            counters_snapshot.extend(attr_value["median"]);
            counters_snapshot.extend(attr_value["deviation"]);

            self.fill_data(filename, timestamp, counters_snapshot)
            xml_child = xml_package.findall("entry")
            if len(xml_child) > 0:
                os.makedirs(db_name, exist_ok=True)
            for c in xml_child:
                self.__build__(c, args, os.path.join(path, item_name), timestamp, method)
        else:
            # means "item"
            attr_value = defaultdict(list)
            for elem in xml_package:
                value = elem.text
                name = elem.tag
                attr_value[name]=value.strip()
            counters_snapshot = []
            counters_snapshot.append(attr_value["mmcc"]);
            counters_snapshot.append(attr_value["tmcc"]);
            counters_snapshot.append(attr_value["sif"]);
            counters_snapshot.append(attr_value["lif"]);
            counters_snapshot.extend(["nan"] * 8)
            self.fill_data(filename, timestamp, counters_snapshot)

    def build(self, rrd_db_create_args, path, timestamp, method):
        xml = self.packaged_tree
        main_package = xml.findall("entry")
        if len(main_package) != 1:
            raise Exception(
                f"Only 1 main package `entry` element is expected in pmccabe xml"
            )
        self.__build__(main_package[0], rrd_db_create_args, path, timestamp, method)

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
    default=supported_methods[0]
)

args = parser.parse_args()

pmccabe_tree_xml = sys.stdin.read()
xml_root = ElementTree.fromstring(pmccabe_tree_xml)

processor = rrd(xml_root)
timestamp="1701154261"
filtered_xml = processor.build(args.args.split(), args.path, timestamp, args.method)
