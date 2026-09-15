#!/usr/bin/env python

import re

from fs_api_wrappers import (
    create_api_query_interruptible,
    execute_read_ids,
    get_normalized_api_queries,
    generate_inner_session_id
)

class DocumentStore:
    def __init__(self, shared_api_dir, main_service_name):
        self.shared_api_dir = shared_api_dir
        self.main_service_name = main_service_name

        # Create API handles
        self.normalized_api_queries = get_normalized_api_queries(
            self.shared_api_dir,
            self.main_service_name,
            {
                # TODO implement read_ids instead of read_id, and use it here
                "read_ids": re.compile(r".*ai_agent_rag_dispatcher.*read_id.*"),
            },
        )
        self.session_id = generate_inner_session_id("document_storage", "ask_question")
        self.put_doc_query = create_api_query_interruptible(
            self.shared_api_dir, self.normalized_api_queries["read_ids"], self.session_id
        )

    def get_many(self, ids: list[str]) -> dict[str, str]:
        if len(ids) == 0:
            return []

        timeout_elapsed = 10 * len(ids)
        return execute_read_ids(self.put_doc_query, self.session_id, timeout_elapsed, ids);
