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

class rrd:
    def __init__(self, p_tree):
        self.packaged_tree = p_tree

    def __build__(self, xml_package, args, path):
        item_name=xml_package.get("package")
        if item_name is None:
            item_name=xml_package.get("file")
        if item_name is None:
            item_name=xml_package.get("item")
        print(f"item_name: {item_name}, path: {path}")
        db_name = os.path.join(path, item_name)
        rrd_create_result = subprocess.run(
            [
                "rrdtool",
                "create",
                f"{db_name}.rrd",
                *args
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        package_statistic = xml_package.findall("statistic")
        if len(package_statistic) == 1:
            attr_value = defaultdict(list)
            for elem in package_statistic[0]:
                value = elem.text
                name = elem.tag
                attr_value[name]=value.split(",")

            xml_child = xml_package.findall("entry")
            if len(xml_child) > 0:
                os.makedirs(db_name, exist_ok=True)
            for c in xml_child:
                self.__build__(c, args, os.path.join(path, item_name))


    def build(self, rrd_db_create_args, path):
        xml = self.packaged_tree
        main_package = xml.findall("entry")
        if len(main_package) != 1:
            raise Exception(
                f"Only 1 main package `entry` element is expected in pmccabe xml"
            )
        self.__build__(main_package[0], rrd_db_create_args, path)

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
args = parser.parse_args()

pmccabe_tree_xml = sys.stdin.read()
xml_root = ElementTree.fromstring(pmccabe_tree_xml)

processor = rrd(xml_root)
filtered_xml = processor.build(args.args.split(), args.path)
