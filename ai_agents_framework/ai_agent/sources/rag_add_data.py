#!/usr/bin/env python
"""Insert inline document data into RAG."""
import base64
import sys
from fs_api_wrappers import execute_put_doc_data_query
from rag_add_utils import ingest_document, run_cli, validate_document_type


def main(shared_api_dir, main_service_name, sess_id, db_host, db_port, doc_data,
         doc_metadata=None, doc_type=None, timeout=20):
    if not doc_type:
        raise ValueError("doc_type is required for inline document data")
    validate_document_type(doc_type)
    def insert(query, session, deadline, dispatcher_type):
        encoded = base64.b64encode(doc_data.encode("utf-8")).decode("ascii")
        return execute_put_doc_data_query(query, session, deadline, encoded,
                                          dispatcher_type, doc_metadata)
    return ingest_document(shared_api_dir, main_service_name, sess_id, db_host, db_port,
                           None, doc_metadata, doc_type, doc_data, timeout,
                           "put_doc_data", insert)


if __name__ == "__main__":
    sys.exit(run_cli(main, inline=True))
