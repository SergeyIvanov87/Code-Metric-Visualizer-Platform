#!/usr/bin/env python

import argparse
import json
import subprocess
import sys

from pathlib import Path

def main():
    parser = argparse.ArgumentParser(prog="Sync documents on a persistent storage")
    args = parser.parse_args()

    secrets_path = Path("/run/secrets")
    db_login_secret_path = secrets_path / "backend_mysql_db_login"
    db_pwd_secret_path = secrets_path / "backend_mysql_db_password"

    backends_path = Path("./backend")
    mysql_backend = backends_path / "mysql"

    mysql_db_uri = "sqlite:///rag_docs_database.db"
    storage_uri = "/package/file_storage"

    sys.path.insert(0, backends_path)
    exec_status = subprocess.run(
        [
            "python",
            "-m",
            "mysql.synchronize_data",
            db_login_secret_path,
            db_pwd_secret_path,
            mysql_db_uri,
            storage_uri,
        ],
        capture_output=True,
        cwd=backends_path,
        text=False,
        shell=False,
    )

    return_data = {"error_code": exec_status.returncode, "error_msg": exec_status.stderr, "output": exec_status.stdout }
    print(return_data)


if __name__ == "__main__":
    sys.exit(main())
