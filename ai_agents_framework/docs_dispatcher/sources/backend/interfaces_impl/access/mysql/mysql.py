"""MySQL/SQLite implementation of the database-neutral record access contract."""

from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Mapping

from sqlalchemy import func, text

from interfaces import RuntimeConfig
from interfaces.access import AccessRecordEntryInterface
from interfaces.store.utils import decanonize_file_uri
from interfaces.schema import RecordSchema
from . import database
from .models import FileRecord


class MysqlAccessRecordEntry(AccessRecordEntryInterface):
    def __init__(self, session):
        self.session = session

    @classmethod
    @contextmanager
    def create_instance(cls, config: RuntimeConfig):
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

    def create_unique_ids(self, count: int = 1) -> Iterable[int]:
        if count < 0:
            raise ValueError("count must be greater than or equal to 0")

        records = [FileRecord(file_path="") for _ in range(count)]
        if not records:
            return ()

        try:
            self.session.add_all(records)
            self.session.flush()
            unique_ids = tuple(int(record.id) for record in records)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return unique_ids

    def create_records_by_ids(
        self,
        records_by_id: Mapping[int, RecordSchema],
    ) -> int:
        if not records_by_id:
            return 0

        record_ids = tuple(int(record_id) for record_id in records_by_id)
        try:
            existing_ids = [
                int(record_id)
                for (record_id,) in (
                    self.session.query(FileRecord.id)
                    .filter(FileRecord.id.in_(record_ids))
                    .all()
                )
            ]
            if existing_ids:
                raise ValueError(
                    f"Records with ids={existing_ids} already exist"
                )

            rows = [
                FileRecord(
                    id=record_id,
                    file_path=decanonize_file_uri(str(record.file_uri)),
                    offset=record.offset,
                    size=record.size,
                    parent_id=record.parent_id,
                    metadata_json=record.metadata,
                    doc_type=record.doc_type,
                )
                for record_id, record in records_by_id.items()
            ]
            self.session.add_all(rows)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return len(rows)

    def update_record_by_id(self, unique_id: int, record: RecordSchema) -> int:
        return self.update_records_by_ids({unique_id: record})

    def update_records_by_ids(self, records_by_id: Mapping[int, RecordSchema]) -> int:
        if not records_by_id:
            return 0

        try:
            rows = (
                self.session.query(FileRecord)
                .filter(FileRecord.id.in_(tuple(records_by_id)))
                .all()
            )
            for row in rows:
                record = records_by_id[int(row.id)]
                row.file_path = decanonize_file_uri(record.file_uri)
                row.offset = record.offset
                row.size = record.size
                row.parent_id = record.parent_id
                row.metadata_json = record.metadata
                row.doc_type = record.doc_type
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return len(rows)

    def get_records(self, record_ids) -> list[RecordSchema]:
        rows = self.session.query(FileRecord).filter(FileRecord.id.in_(list(record_ids))).all()
        return [self._record(row) for row in rows]

    def get_all_records(self) -> list[RecordSchema]:
        return [self._record(row) for row in self.session.query(FileRecord).all()]

    def delete_records(
        self,
        record_ids: Iterable[int],
        cascade_delete: bool = True,
    ) -> tuple[int, list[int]]:
        requested_ids = _unique_ids(record_ids)
        requested_records = self.get_records(requested_ids)
        records_by_id = {
            int(record.id): record
            for record in requested_records
        }
        missing_ids = [
            record_id
            for record_id in requested_ids
            if record_id not in records_by_id
        ]
        target_ids = list(records_by_id)

        if cascade_delete:
            deleted_parent_ids = [
                record_id
                for record_id, record in records_by_id.items()
                if record.id == record.parent_id
            ]
            if deleted_parent_ids:
                chunk_rows = (
                    self.session.query(FileRecord.id)
                    .filter(
                        FileRecord.parent_id.in_(deleted_parent_ids),
                        FileRecord.id != FileRecord.parent_id,
                    )
                    .all()
                )
                target_ids.extend(int(record_id) for (record_id,) in chunk_rows)

        target_ids = _unique_ids(target_ids)
        deleted_count = self._delete_records(target_ids) if target_ids else 0

        return deleted_count, missing_ids

    @staticmethod
    def _record(row) -> RecordSchema | None:
        if row is None:
            return None
        return RecordSchema(
            file_uri=row.file_path,
            id=row.id,
            offset=row.offset,
            size=row.size,
            parent_id=row.parent_id,
            metadata=row.metadata_json,
            doc_type=row.doc_type,
        )

    def _get_chunk_ids(self, document_ids: Iterable[int]) -> dict[int, list[int]]:
        requested_ids = _unique_ids(document_ids)
        chunk_ids_by_document = {document_id: [] for document_id in requested_ids}
        if not requested_ids:
            return chunk_ids_by_document

        rows = (
            self.session.query(FileRecord.parent_id, FileRecord.id)
            .filter(
                FileRecord.parent_id.in_(requested_ids),
                FileRecord.id != FileRecord.parent_id,
            )
            .order_by(FileRecord.parent_id, FileRecord.id)
            .all()
        )
        for parent_id, chunk_id in rows:
            chunk_ids_by_document[int(parent_id)].append(int(chunk_id))

        return chunk_ids_by_document

    def document_page(self, offset: int, limit: int) -> tuple[int, list[RecordSchema]]:
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

    def _delete_records(self, record_ids) -> int:
        try:
            deleted_count = self.session.query(FileRecord).filter(
                FileRecord.id.in_(list(record_ids))
            ).delete(synchronize_session=False)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return deleted_count

def _unique_ids(doc_ids: Iterable[int]) -> list[int]:
    return list(dict.fromkeys(doc_ids))
