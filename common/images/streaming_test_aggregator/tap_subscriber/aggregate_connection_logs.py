#!/usr/bin/env python3

"""Combine immutable per-connection logs into one ordered log per producer."""

import argparse
import re
from collections import defaultdict
from pathlib import Path


CONNECTION_LOG = re.compile(r"^(?P<producer>.+)__connection_(?P<id>\d+)\.log$")


def aggregate(connection_directory, output_directory):
    producers = defaultdict(list)
    for path in connection_directory.iterdir():
        if not path.is_file():
            continue
        match = CONNECTION_LOG.match(path.name)
        if match:
            producers[match.group("producer")].append(
                (int(match.group("id")), path)
            )

    output_directory.mkdir(parents=True, exist_ok=True)
    for producer, connections in producers.items():
        output_file = output_directory / f"{producer}.log"
        temporary = output_file.with_suffix(".log.tmp")
        with temporary.open("wb") as combined:
            for _, connection in sorted(connections):
                combined.write(connection.read_bytes())
        temporary.replace(output_file)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("connection_directory", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    aggregate(args.connection_directory, args.output_directory)


if __name__ == "__main__":
    main()
