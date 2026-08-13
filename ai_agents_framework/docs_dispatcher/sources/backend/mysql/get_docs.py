#!/usr/bin/env python

import argparse
import json
import sys

from mysql.app import crud
from mysql.app.database import create_engine, create_session, initialize_schema
from mysql.config import load_mysql_backend_config
from mysql.utils import decanonize_file_uri


_UNLIMITED_ROW_COUNT = 9223372036854775807


def _documents_count_query() -> str:
    return "SELECT COUNT(*) AS total_documents FROM file_records WHERE id = parent_id"


def _documents_query(offset: int, limit: int) -> str:
    row_limit = _UNLIMITED_ROW_COUNT if limit == -1 else limit
    return (
        "SELECT id, file_path, doc_type FROM file_records "
        "WHERE id = parent_id "
        "ORDER BY id "
        f"LIMIT {row_limit} OFFSET {offset}"
    )


def _chunks_query(document_id: int) -> str:
    return (
        "SELECT id FROM file_records "
        f"WHERE parent_id = {document_id} AND id != parent_id "
        "ORDER BY id"
    )


def get_documents(session, offset: int = 0, limit: int = -1) -> dict[str, object]:
    if offset < 0:
        raise ValueError("offset must be greater than or equal to 0")
    if limit < -1:
        raise ValueError("limit must be -1 or greater")

    count_row = crud.execute_query(session, _documents_count_query()).fetchone()
    total_documents = int(count_row._mapping["total_documents"])
    document_rows = crud.execute_query(session, _documents_query(offset, limit)).fetchall()
    documents = []
    for document_row in document_rows:
        document = document_row._mapping
        chunk_rows = crud.execute_query(session, _chunks_query(int(document["id"]))).fetchall()
        documents.append(
            {
                "id": int(document["id"]),
                "file_uri": decanonize_file_uri(document["file_path"]),
                "type": document["doc_type"],
                "chunks": [int(chunk._mapping["id"]) for chunk in chunk_rows],
            }
        )
    returned_limit = len(documents)
    return {
        "offset": offset,
        "limit": returned_limit,
        "remaining": max(0, total_documents - offset - returned_limit),
        "docs": documents,
    }


def main():
    parser = argparse.ArgumentParser(prog="List documents using MYSQL backend")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=-1)
    args = parser.parse_args()

    try:
        backend_config = load_mysql_backend_config()
        if backend_config.db_uri.find("sqlite:///") == -1:
            engine = create_engine(
                backend_config.db_login_secret_path,
                backend_config.db_pwd_secret_path,
                backend_config.db_uri,
            )
        else:
            engine = create_engine(backend_config.db_uri)

        initialize_schema(engine)
        with create_session(engine) as session:
            result = get_documents(session, args.offset, args.limit)
        error_code = 0
    except Exception as ex:
        result = {"error_code": -1, "error_msg": str(ex)}
        error_code = -1

    print(json.dumps(result))
    return error_code


if __name__ == "__main__":
    sys.exit(main())
