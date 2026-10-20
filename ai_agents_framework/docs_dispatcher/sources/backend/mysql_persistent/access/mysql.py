"""MySQL/SQLite implementation of the database-neutral record access contract."""

from contextlib import contextmanager
from pathlib import Path
from dataclasses import fields

from sqlalchemy import func, or_, text

from interfaces import RuntimeConfig
from interfaces.access import AccessRecord, AccessRecordEntryInterface
from . import crud, database
from .models import FileRecord


class MysqlAccessRecordEntry(AccessRecordEntryInterface):
    def __init__(self, session):
        self.session = session

    @classmethod
    @contextmanager
    def open(cls, config: RuntimeConfig):
        options = config.options
        db_uri = options.get("mysql_db_uri", options.get("db_uri"))
        if not db_uri:
            raise ValueError("MySQL access requires mysql_db_uri or db_uri")
        if "sqlite:///" in db_uri:
            engine = database.create_engine(db_uri)
        else:
            engine = database.create_engine(Path(options["db_login_secret"]),
                                            Path(options["db_pwd_secret"]), db_uri)
        try:
            database.initialize_schema(engine)
            with database.create_session(engine) as session:
                yield cls(session)
        finally:
            engine.dispose()

    @staticmethod
    def _record(row) -> AccessRecord | None:
        if row is None:
            return None
        return AccessRecord(**{field.name: getattr(row, field.name) for field in fields(AccessRecord)})

    def create_record(self, record: AccessRecord, *, preserve_id: bool = False) -> AccessRecord:
        args = (record.file_path, record.offset, record.size, record.parent_id)
        kwargs = dict(metadata_json=record.metadata_json, doc_type=record.doc_type)
        if preserve_id:
            row = crud.create_file_record_with_uid(self.session, record.id, *args, **kwargs)
        else:
            row = crud.create_file_record(self.session, *args, **kwargs)
        return self._record(row)

    def get_file_record(self, record_id: int) -> AccessRecord | None:
        return self._record(crud.get_file_record(self.session, record_id))

    def get_all_records(self) -> list[AccessRecord]:
        return [self._record(row) for row in crud.get_all_records(self.session)]

    def update_file_record_ext(self, record_id: int, record: AccessRecord) -> AccessRecord | None:
        return self._record(crud.update_file_record_ext(self.session, record_id, record))

    def delete_file_record(self, record_id: int) -> bool:
        return crud.delete_file_record(self.session, record_id)

    def get_records(self, record_ids) -> list[AccessRecord]:
        rows = self.session.query(FileRecord).filter(FileRecord.id.in_(list(record_ids))).all()
        return [self._record(row) for row in rows]

    def get_documents(self, offset: int, limit: int) -> tuple[int, list[AccessRecord]]:
        total = self.session.query(func.count(FileRecord.id)).filter(FileRecord.id == FileRecord.parent_id).scalar()
        if offset < 0 or limit < -1:
            raise ValueError("Invalid document pagination")
        row_limit = 9223372036854775807 if limit == -1 else limit
        statement = (
            "SELECT * FROM file_records WHERE id = parent_id ORDER BY id "
            f"LIMIT {int(row_limit)} OFFSET {int(offset)}"
        )
        rows = self.session.query(FileRecord).from_statement(text(statement)).all()
        return int(total), [self._record(row) for row in rows]

    def get_chunk_ids(self, document_id: int) -> list[int]:
        rows = (self.session.query(FileRecord.id)
                .filter(FileRecord.parent_id == document_id, FileRecord.id != document_id)
                .order_by(FileRecord.id).all())
        return [int(record_id) for (record_id,) in rows]

    def get_related_records(self, record_ids) -> list[AccessRecord]:
        ids = list(record_ids)
        rows = self.session.query(FileRecord).filter(
            or_(FileRecord.id.in_(ids), FileRecord.parent_id.in_(ids))).all()
        return [self._record(row) for row in rows]

    def delete_records(self, record_ids) -> None:
        self.session.query(FileRecord).filter(FileRecord.id.in_(list(record_ids))).delete(synchronize_session=False)
        self.session.commit()
