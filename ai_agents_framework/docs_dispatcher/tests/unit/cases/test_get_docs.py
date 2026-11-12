from interfaces_impl.access.mysql import MysqlAccessRecordEntry
from interfaces.schema import RecordSchema
from interfaces_impl.store.persistent import PersistentStorageRecordEntry
from mysql_persistent.backend import MysqlPersistentBackend
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


from interfaces_impl.access.mysql.database import Base



def _document(session, file_uri: str, doc_type: str = "txt"):
    access = MysqlAccessRecordEntry(session)
    record_id = next(iter(access.create_unique_ids()))
    document = RecordSchema(
        file_uri=file_uri,
        id=record_id,
        offset=0,
        size=10,
        parent_id=record_id,
        doc_type=doc_type,
    )
    assert access.update_record_by_id(record_id, document) == 1
    return document


def _chunk(session, document_id: int, file_uri: str):
    access = MysqlAccessRecordEntry(session)
    record_id = next(iter(access.create_unique_ids()))
    chunk = RecordSchema(
        file_uri=file_uri,
        id=record_id,
        offset=0,
        size=5,
        parent_id=document_id,
    )
    assert access.update_record_by_id(record_id, chunk) == 1
    return chunk


def _backend(session, storage_root):
    return MysqlPersistentBackend(
        access=MysqlAccessRecordEntry(session),
        store=PersistentStorageRecordEntry(storage_root),
    )


def test_get_documents_returns_decanonized_uris_and_chunk_ids_with_limit_pagination(tmp_path):
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
    first_chunk = _chunk(session, first.id, first.file_uri)
    second_chunk_1 = _chunk(session, second.id, second.file_uri)
    second_chunk_2 = _chunk(session, second.id, second.file_uri)

    assert _backend(session, tmp_path).get_documents(offset=1, limit=1) == {
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


def test_get_documents_limit_zero_returns_empty_docs_array(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    _document(session, "/docs/first.txt")

    assert _backend(session, tmp_path).get_documents(offset=0, limit=0) == {
        "offset": 0,
        "limit": 0,
        "remaining": 1,
        "docs": [],
    }

    session.close()


def test_get_documents_remaining_never_becomes_negative(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    _document(session, "/docs/first.txt")

    assert _backend(session, tmp_path).get_documents(offset=5, limit=1) == {
        "offset": 5,
        "limit": 0,
        "remaining": 0,
        "docs": [],
    }

    session.close()
