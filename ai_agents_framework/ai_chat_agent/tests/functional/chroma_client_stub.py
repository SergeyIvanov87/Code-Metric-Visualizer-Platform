"""Functional-only Chroma client stub, loaded as ``sitecustomize``."""

import os
import sys


POSITIVE_SESSION_ID = "rrd_microservice_document_found"
NEGATIVE_SESSION_ID = "rrd_microservice_document_not_found"


class _Collection:
    def __init__(self, session_id):
        self.session_id = session_id

    def query(self, **_kwargs):
        if self.session_id == NEGATIVE_SESSION_ID:
            return {"ids": [[]], "distances": [[]]}
        if self.session_id == POSITIVE_SESSION_ID:
            return {"ids": [["9900"]], "distances": [[0.0]]}
        raise RuntimeError(f"no Chroma stub data for session {self.session_id!r}")


class _Client:
    def __init__(self, session_id):
        self.session_id = session_id

    def get_collection(self, **_kwargs):
        return _Collection(self.session_id)


def _session_id():
    prefix = "--session_id="
    return next(
        (argument[len(prefix):] for argument in sys.argv if argument.startswith(prefix)),
        "",
    )


if os.path.basename(sys.argv[0]) == "agentic_rag.py":
    import chromadb

    chromadb.HttpClient = lambda **_kwargs: _Client(_session_id())
