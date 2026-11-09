#!/usr/bin/env python

import argparse
import json
import sys

from backend.dispatcher.dispatcher import BackendDispatcher

def main():
    parser = argparse.ArgumentParser(prog="Sync documents on a persistent storage")
    parser.parse_args()

    try:
        with BackendDispatcher().get_backend() as backend:
            result = backend.access.synchronize(backend.store)
        result = {"error_code": 0, **result}
    except Exception as ex:
        result = {"error_code": -1, "error_msg": str(ex)}
    print(json.dumps(result))
    return result["error_code"]


if __name__ == "__main__":
    sys.exit(main())
