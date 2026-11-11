"""MySQL/SQLite implementation of the database-neutral record access contract."""

import base64
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import func, text

from interfaces import RuntimeConfig
from interfaces.access import AccessRecordEntryInterface
from interfaces.store.utils import decanonize_file_uri, file_uris_equal, prepare_doc_data
from interfaces.schema import RecordSchema
from interfaces.store import StorageRecordEntryInterface
from . import database
from .models import FileRecord

_SYNC_FIELDS = ("file_path", "offset", "size", "parent_id", "doc_type")


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

    ####### recondider the rest
    def create_file_record(
        self,
        file_path: str,
        offset: int,
        size: int,
        parent_id: int,
        metadata_json: Optional[dict[str, Any]] = None,
        doc_type: str = "",
    ) -> RecordSchema:

        record = FileRecord(
            file_path=decanonize_file_uri(file_path),
            offset=offset,
            size=size,
            parent_id=parent_id,
            metadata_json=metadata_json,
            doc_type=doc_type,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return self._record(record)

    def create_file_record_with_uid(
        self,
        uid: int,
        file_path: str,
        offset: int,
        size: int,
        parent_id: int,
        metadata_json: Optional[dict[str, Any]] = None,
        doc_type: str = "",
    ) -> RecordSchema:
        existing = self.session.query(FileRecord).filter(FileRecord.id == uid).first()
        if existing:
            raise ValueError(f"Record with id={uid} already exists")

        record = FileRecord(
            id=uid,
            file_path=decanonize_file_uri(file_path),
            offset=offset,
            size=size,
            parent_id=parent_id,
            metadata_json=metadata_json,
            doc_type=doc_type,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return self._record(record)

    def create_file_record_ext(self, record: FileRecord | RecordSchema) -> RecordSchema:
        record.file_path = decanonize_file_uri(record.file_path)
        record = FileRecord(
            id=record.id,
            file_path=record.file_path,
            offset=record.offset,
            size=record.size,
            parent_id=record.parent_id,
            metadata_json=record.metadata_json,
            doc_type=record.doc_type,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return self._record(record)

    def _get_row(self, record_id: int) -> Optional[FileRecord]:
        return self.session.query(FileRecord).filter(FileRecord.id == record_id).first()

    def execute_query(self, query_str: str):
        result = self.session.execute(text(query_str))
        normalized = query_str.lstrip().lower()
        if not normalized.startswith("select"):
            self.session.commit()
        return result

    def update_file_record(
        self,
        record_id: int,
        *,
        file_path: Optional[str] = None,
        offset: Optional[int] = None,
        size: Optional[int] = None,
        parent_id: Optional[int] = None,
        metadata_json: Optional[dict[str, Any]] = None,
        doc_type: Optional[str] = None,
    ) -> Optional[RecordSchema]:
        record = self._get_row(record_id)
        if not record:
            return None

        if file_path is not None:
            record.file_path = decanonize_file_uri(file_path)
        if offset is not None:
            record.offset = offset
        if size is not None:
            record.size = size
        if parent_id is not None:
            record.parent_id = parent_id
        if metadata_json is not None:
            record.metadata_json = metadata_json
        if doc_type is not None:
            record.doc_type = doc_type

        self.session.commit()
        self.session.refresh(record)
        return self._record(record)

    def update_file_record_ext(
        self,
        record_id: int,
        new_record: FileRecord | RecordSchema,
    ) -> Optional[RecordSchema]:
        record = self._get_row(record_id)
        if not record:
            return None

        for field in _SYNC_FIELDS:
            value = getattr(new_record, field)
            if field == "file_path":
                value = decanonize_file_uri(value)
            setattr(record, field, value)

        self.session.commit()
        self.session.refresh(record)
        return self._record(record)

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

    def synchronize_records(
        self,
        all_db_records: list[RecordSchema],
        storage_records: dict[int, RecordSchema],
    ) -> dict:
        remaining_storage = dict(storage_records)

        updated = 0
        untouched = len(remaining_storage)

        record_ids_to_delete = []
        db_records_to_update: list[RecordSchema] = []
        for db_record in all_db_records:
            if db_record.id not in remaining_storage:
                record_ids_to_delete.append(db_record.id)
                continue
            db_records_to_update.append(db_record)

        deleted, _ = self.delete_records(
            record_ids_to_delete,
            cascade_delete=False,
        )

        for db_record in db_records_to_update:
            storage_record = remaining_storage[db_record.id]
            is_updated, db_record = apply_storage_fields_to_db_record(
                db_record,
                storage_record,
            )
            if is_updated:
                self.update_file_record_ext(db_record.id, db_record)
                updated += 1

            remaining_storage.pop(db_record.id)

        created = len(remaining_storage)
        untouched = untouched - updated - created

        for storage_record in remaining_storage.values():
            self.create_file_record_with_uid(storage_record.id,
                decanonize_file_uri(str(storage_record.file_uri)),
                storage_record.offset,
                storage_record.size,
                storage_record.parent_id,
                metadata_json=storage_record.metadata,
                doc_type=storage_record.doc_type,
            )

        return {
            "created": created,
            "updated": updated,
            "deleted": deleted,
            "not_changed": untouched,
        }

    #removing TODO
    def synchronize(self, store: StorageRecordEntryInterface) -> dict:
        store.ensure_root()
        db_records = self.get_all_records()
        storage_records = store.get_all_records()
        return {**self.synchronize_records(db_records, storage_records),
                "initial DB records": len(db_records), "storage size": len(storage_records)}


    def rebuild_table_from_directory(
        self,
        directory_path: str,
        clear_existing: bool = True,
    ) -> None:
        """Rebuild table content from files in a directory."""
        directory = Path(directory_path)

        if not directory.exists():
            raise ValueError(f"Directory does not exist: {directory_path}")
        if not directory.is_dir():
            raise ValueError(f"Not a directory: {directory_path}")

        if clear_existing:
            self.session.query(FileRecord).delete()
            self.session.commit()

        for root, _, files in os.walk(directory):
            for filename in files:
                full_path = Path(root) / filename
                record = FileRecord(
                    file_path=str(full_path.resolve()),
                    offset=0,
                    size=full_path.stat().st_size,
                    parent_id=0,
                    metadata_json={},
                    doc_type="",
                )
                self.session.add(record)

        self.session.commit()


def _unique_ids(doc_ids: Iterable[int]) -> list[int]:
    return list(dict.fromkeys(doc_ids))

def _is_db_document(record: RecordSchema | None, doc_id: int) -> bool:
    return record is not None and int(record.parent_id) == doc_id

def _is_storage_document(record: RecordSchema | None, doc_id: int) -> bool:
    return record is not None and record.parent_id == doc_id

def _db_info(
    access,
    document: RecordSchema,
) -> dict[str, object]:
    document_id = int(document.id)
    chunks = access._get_chunk_ids([document_id])[document_id]
    return {
        "file_uri": decanonize_file_uri(document.file_path),
        "type": document.doc_type,
        "chunks": chunks,
    }

def _storage_info(
    document: RecordSchema,
    storage_records: dict[int, RecordSchema],
) -> dict[str, object]:
    chunk_ids = sorted(
        record_id
        for record_id, record in storage_records.items()
        if record_id != document.id and record.parent_id == document.id
    )
    return {
        "file_uri": decanonize_file_uri(document.file_uri),
        "type": document.doc_type,
        "chunks": chunk_ids,
    }

def apply_storage_fields_to_db_record(
    db_record: RecordSchema,
    storage_record: RecordSchema,
) -> tuple[bool, RecordSchema]:
    changed = False

    storage_path = decanonize_file_uri(str(storage_record.file_uri))
    if not file_uris_equal(db_record.file_path, storage_record.file_uri):
        db_record.file_path = storage_path
        changed = True
    if db_record.offset != storage_record.offset:
        db_record.offset = storage_record.offset
        changed = True
    if db_record.size != storage_record.size:
        db_record.size = storage_record.size
        changed = True
    if db_record.parent_id != storage_record.parent_id:
        db_record.parent_id = storage_record.parent_id
        changed = True
    if db_record.doc_type != storage_record.doc_type:
        db_record.doc_type = storage_record.doc_type
        changed = True

    return changed, db_record

SUCCESS = "success"
MISSING_DATABASE = "Not found in the doc storage: database"
MISSING_FILE_STORAGE = "Not found in the doc storage: file storage"
ABSENT_OR_INVALID = "The doc is absent or ID is incorrect"
