from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from mysql.app.crud import create_file_record, update_file_record
from mysql.app.database import Base
from mysql.get_docs import get_documents


def _document(session, file_uri: str, doc_type: str = "txt"):
    document = create_file_record(session, file_uri, 0, 10, 0, doc_type=doc_type)
    update_file_record(session, document.id, parent_id=document.id)
    return document


def _chunk(session, document_id: int, file_uri: str):
    return create_file_record(session, file_uri, 0, 5, document_id)


def test_get_documents_returns_decanonized_uris_and_chunk_ids_with_limit_pagination():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    statements = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda conn, cursor, statement, parameters, context, executemany: statements.append(statement),
    )

    first = _document(session, "%slash%docs%slash%first.txt")
    second = _document(session, "%slash%docs%slash%second.txt", "markdown")
    first_chunk = _chunk(session, first.id, first.file_path)
    second_chunk_1 = _chunk(session, second.id, second.file_path)
    second_chunk_2 = _chunk(session, second.id, second.file_path)

    assert get_documents(session, offset=1, limit=1) == {
        "offset": 1,
        "limit": 1,
        "remaining": 0,
        "docs": [{
            "id": second.id,
            "file_uri": "/docs/second.txt",
            "type": "markdown",
            "chunks": [second_chunk_1.id, second_chunk_2.id],
        }],
    }
    assert any("LIMIT 1 OFFSET 1" in statement for statement in statements)
    assert first_chunk.id not in [second_chunk_1.id, second_chunk_2.id]

    session.close()


def test_get_documents_limit_zero_returns_empty_docs_array():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    _document(session, "/docs/first.txt")

    assert get_documents(session, offset=0, limit=0) == {
        "offset": 0,
        "limit": 0,
        "remaining": 1,
        "docs": [],
    }

    session.close()


def test_get_documents_remaining_never_becomes_negative():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    _document(session, "/docs/first.txt")

    assert get_documents(session, offset=5, limit=1) == {
        "offset": 5,
        "limit": 0,
        "remaining": 0,
        "docs": [],
    }

    session.close()
