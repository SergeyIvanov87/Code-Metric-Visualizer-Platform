#!/usr/bin/env python

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(prog="Attach document chunk using assigned backend")
    parser.add_argument("-doc_id", "--doc_id", type=int, help="Parent document id")
    parser.add_argument("-metadata", "--metadata", type=str, help="chunk metadata")

    args = parser.parse_args()

    secrets_path = Path("/run/secrets")
    db_login_secret_path = secrets_path / "backend_mysql_db_login"
    db_pwd_secret_path = secrets_path / "backend_mysql_db_password"

    backends_path = Path("./backend")
    mysql_backend = backends_path / "mysql"

    mysql_db_uri = "sqlite:///rag_docs_database.db"
    storage_uri = "/package/file_storage"

    sys.path.insert(0, str(backends_path))
    chunk_data = sys.stdin.read()
    exec_status = subprocess.run(
        [
            "python",
            "-m",
            "mysql.attach_doc_chunk",
            db_login_secret_path,
            db_pwd_secret_path,
            mysql_db_uri,
            storage_uri,
            str(args.doc_id),
            "-m",
            args.metadata,
        ],
        input=chunk_data.encode(),
        capture_output=True,
        cwd=backends_path,
        text=False,
        shell=False,
    )

    output = json.loads(exec_status.stdout.decode('utf-8'))
    return_data = {}
    return_data = return_data | output
    print(json.dumps(return_data))



if __name__ == "__main__":
    sys.exit(main())
