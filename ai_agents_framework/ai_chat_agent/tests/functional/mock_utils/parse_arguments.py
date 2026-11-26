#!/usr/bin/env python3


def parse_arguments(arguments):
    session_id = None
    query = {}
    index = 0
    while index < len(arguments):
        name = arguments[index]
        if name.startswith("SESSION_ID="):
            session_id = name.split("=", 1)[1]
            index += 1
            continue
        if index + 1 == len(arguments):
            raise ValueError(f"missing value for {name}")
        value = arguments[index + 1]
        if name == "SESSION_ID":
            session_id = value
        else:
            query[name] = value
        index += 2
    return session_id, query
