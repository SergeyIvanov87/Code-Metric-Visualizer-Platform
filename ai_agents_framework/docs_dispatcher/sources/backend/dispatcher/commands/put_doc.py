#!/usr/bin/env python

import argparse
import base64
import json
import sys

from pathlib import Path
from dispatcher.runtime import get_backend
from dispatcher.runtime_config import load_runtime_config
from interfaces.store.operations import add_abstract_document
from interfaces.access.utils import prepare_doc_data

parent_id_for_orphants = 0

def main():
    parser = argparse.ArgumentParser(prog="Insert document using selected backend")
    parser.add_argument("file_uri", type=Path, nargs='?', default=None, help="file URI")
    parser.add_argument("-m", "--metadata", type=str, help="file metadata")
    parser.add_argument("-doc_type", "--doc_type", type=str, default="txt", help="document type")

    args = parser.parse_args()
    backend_config = load_runtime_config()
    metadata = args.metadata or ""
    doc_type = args.doc_type or ""

    ret = {"error_code": 0}
    try:
        # read document data
        if args.file_uri is None:
            document_data = sys.stdin.read().encode('utf-8')
            if "base64" in doc_type:
                document_data = base64.b64decode(document_data)
        else:
            with open(args.file_uri,'rb') as f:
                document_data = f.read()

        document_data = prepare_doc_data(document_data)

        document_db_record = None
        global parent_id_for_orphants
        with get_backend().access.open(backend_config) as access:
            document_db_record = access.create_file_record(str(args.file_uri),
                0,
                len(document_data),
                parent_id_for_orphants,
                metadata_json={"comment": metadata} if metadata else {},
                doc_type=doc_type,
            )

            storage_record = add_abstract_document(backend_config.storage_uri, args.file_uri, document_db_record.id, document_data)
            storage_record.commit_doc(
                backend_config.storage_uri,
                offset=document_db_record.offset,
                metadata_text=metadata,
                doc_type=doc_type,
            )

            document_db_record.parent_id = storage_record.unique_id
            access.update_file_record_ext(document_db_record.id, document_db_record)

        ret["unique_id"] = storage_record.unique_id
    except Exception as ex:
        ret["error_code"] = -1
        ret["error_msg"] = str(ex)

    print(json.dumps(ret))

if __name__ == "__main__":
    sys.exit(main())
