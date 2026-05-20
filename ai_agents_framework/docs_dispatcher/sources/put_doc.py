#!/usr/bin/env python

import argparse
import json
import subprocess
import sys

from pathlib import Path

def main():
    parser = argparse.ArgumentParser(prog="Insert document using assigned backend")
    parser.add_argument("file_uri", type=Path, help="file URI")
    parser.add_argument("metadata", type=Path, help="file metadata")

    args = parser.parse_args()

    # read stdin
    #document_data = sys.stdin.read()

    secrets_path = Path("/run/secrets")
    db_login_secret_path = secrets_path / "backend_mysql_db_login"
    db_pwd_secret_path = secrets_path / "backend_mysql_db_password"

    backends_path = Path("./backend")
    mysql_backend = backends_path / "mysql"

    mysql_db_uri = "sqlite:///rag_docs_database.db"
    storage_uri = "/package/file_storage"
    #[mysql_backend / "put_document.py", db_login_secret_path, db_pwd_secret_path, mysql_db_uri, storage_uri, args.file_uri, args.metadata]

    sys.path.insert(0, backends_path)
    document_data = sys.stdin.read()
    exec_status = subprocess.run(
        [
            "python",
            "-m",
            "mysql.put_document",
            db_login_secret_path,
            db_pwd_secret_path,
            mysql_db_uri,
            storage_uri,
            args.file_uri,
            "-m",
            args.metadata,
        ],
        input=document_data.encode(),
        capture_output=True,
        cwd=backends_path,
        text=False,
        shell=False,
    )
    #exec_status = subprocess.run(["python", "-m", "mysql.put_document"], stdin=sys.stdin, capture_output=True, cwd=backends_path, text=False, shell=False)

    return_data = {"error_code": exec_status.returncode, "error_msg": exec_status.stderr, "unique_id": exec_status.stdout }
    #print(json.dumps(return_data))
    print(return_data)


if __name__ == "__main__":
    sys.exit(main())
