#!/usr/bin/env python

import argparse
import json
import sys

from pathlib import Path
from mysql.app import crud
from mysql.app.database import create_engine, create_session, Base
from mysql.app.models import FileRecord
from mysql.config import load_mysql_backend_config
from mysql.doc_storage import operations as doc_storage_operations
from mysql.doc_storage.models import StorageRecord
from mysql.doc_storage.operations import add_abstract_document
from mysql.utils import prepare_doc_data

parent_id_for_orphants = 0

def main():
    parser = argparse.ArgumentParser(prog="Insert document using MYSQL backend")
    parser.add_argument("file_uri", type=Path, help="file URI")
    parser.add_argument("-m", "--metadata", type=str, help="file metadata")

    args = parser.parse_args()
    backend_config = load_mysql_backend_config()

    # read stdin
    document_data = sys.stdin.read()
    document_data = prepare_doc_data(document_data)

    login = None
    password = None
    engine = None

    ret = {"error_code": 0}
    try:
        if backend_config.db_uri.find("sqlite:///") == -1:
            login = backend_config.db_login_secret_path
            password = backend_config.db_pwd_secret_path
            engine = create_engine(login, password, backend_config.db_uri)
        else:
            engine = create_engine(backend_config.db_uri)

        Base.metadata.create_all(engine)

        document_db_record = None
        global parent_id_for_orphants
        with create_session(engine) as session:
            document_db_record = crud.create_file_record(session, str(args.file_uri), 0, len(document_data), parent_id_for_orphants)

        storage_record = add_abstract_document(backend_config.storage_uri, args.file_uri, document_db_record.id, document_data)
        storage_record.commit_doc(backend_config.storage_uri, offset = document_db_record.offset)

        document_db_record.parent_id = storage_record.unique_id
        crud.update_file_record_ext(session, document_db_record.id, document_db_record)

        ret["unique_id"] = storage_record.unique_id
    except Exception as ex:
        ret["error_code"] = -1
        ret["error_msg"] = str(ex)

    print(json.dumps(ret))

if __name__ == "__main__":
    sys.exit(main())
