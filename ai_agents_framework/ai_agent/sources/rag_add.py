#!/usr/bin/env python
"""Insert a file URI into RAG."""
import sys
from pathlib import Path
from doc_type_association import document_type
from fs_api_wrappers import execute_put_doc_query
from rag_add_utils import ingest_document, run_cli, validate_document_type


def main(shared_api_dir, main_service_name, sess_id, db_host, db_port, doc_uri,
         doc_metadata=None, doc_type=None, timeout=20, preserveOriginal=1):
    if not doc_uri:
        raise ValueError("URI is required")
    resolved_type = doc_type or document_type(doc_uri)
    validate_document_type(resolved_type)
    document = Path(doc_uri).read_bytes().decode("utf-8")
    def insert(query, session, deadline, dispatcher_type):
        return execute_put_doc_query(query, session, deadline, doc_uri,
                                     dispatcher_type, doc_metadata, preserveOriginal)
    return ingest_document(shared_api_dir, main_service_name, sess_id, db_host, db_port,
                           doc_uri, doc_metadata, resolved_type, document, timeout,
                           "put_doc", insert)


if __name__ == "__main__":
    sys.exit(run_cli(main))
