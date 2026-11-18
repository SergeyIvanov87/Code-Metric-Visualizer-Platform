"""Store encoded text chunks through the dispatcher."""
import base64
from fs_api_wrappers import execute_attach_doc_chunks_query


def attach_chunks(query, session_id, document_id, doc_type, metadata, texts):
    try:
        encoded = [base64.b64encode(text.encode("utf-8")).decode("ascii") for text in texts]
        return execute_attach_doc_chunks_query(
            query, session_id, 10 * len(encoded), document_id,
            doc_type, metadata, encoded,
        )
    except Exception as error:
        raise RuntimeError(
            f"Cannot attach chunks: {len(texts)} to doc id: {document_id}, session: {session_id}, exception: {error}"
        ) from error
