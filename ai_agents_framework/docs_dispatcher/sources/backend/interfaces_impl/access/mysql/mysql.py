"""MySQL/SQLite implementation of the database-neutral record access contract."""

import base64
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Optional

from sqlalchemy import func, or_, text

from interfaces import RuntimeConfig
from interfaces.access import AccessRecordEntryInterface
from interfaces.access.utils import decanonize_file_uri, file_uris_equal, prepare_doc_data
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

    def get_all_records(self) -> list[RecordSchema]:
        return [self._record(row) for row in self.session.query(FileRecord).all()]

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

    def delete_file_record(self, record_id: int) -> bool:
        record = self._get_row(record_id)
        if not record:
            return False

        self.session.delete(record)
        self.session.commit()
        return True

    def get_file_record(self, record_id: int) -> RecordSchema | None:
        return self._record(self._get_row(record_id))

    def get_records(self, record_ids) -> list[RecordSchema]:
        rows = self.session.query(FileRecord).filter(FileRecord.id.in_(list(record_ids))).all()
        return [self._record(row) for row in rows]

    def _document_page(self, offset: int, limit: int) -> tuple[int, list[RecordSchema]]:
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

    def _get_chunk_ids(self, document_id: int) -> list[int]:
        rows = (self.session.query(FileRecord.id)
                .filter(FileRecord.parent_id == document_id, FileRecord.id != document_id)
                .order_by(FileRecord.id).all())
        return [int(record_id) for (record_id,) in rows]

    def _get_related_records(self, record_ids) -> list[RecordSchema]:
        ids = list(record_ids)
        rows = self.session.query(FileRecord).filter(
            or_(FileRecord.id.in_(ids), FileRecord.parent_id.in_(ids))).all()
        return [self._record(row) for row in rows]

    def _delete_records(self, record_ids) -> None:
        self.session.query(FileRecord).filter(FileRecord.id.in_(list(record_ids))).delete(synchronize_session=False)
        self.session.commit()

    def get_documents(self, offset: int = 0, limit: int = -1) -> dict[str, object]:
        if offset < 0:
            raise ValueError("offset must be greater than or equal to 0")
        if limit < -1:
            raise ValueError("limit must be -1 or greater")

        total_documents, document_rows = self._document_page(offset, limit)
        documents = [
            {
                "id": int(document.id),
                "file_uri": decanonize_file_uri(document.file_path),
                "type": document.doc_type,
                "chunks": self._get_chunk_ids(document.id),
            }
            for document in document_rows
        ]
        returned_limit = len(documents)
        return {
            "offset": offset,
            "limit": returned_limit,
            "remaining": max(0, total_documents - offset - returned_limit),
            "docs": documents,
        }

    def get_document_info(
        self,
        store: StorageRecordEntryInterface,
        doc_ids: list[int],
    ) -> dict[str, object]:
        requested_ids = _unique_ids(doc_ids)
        storage_records = store.get_all_records()
        found: list[int] = []
        inconsistent: list[int] = []
        not_found: list[int] = []
        result: dict[str, object] = {
            "found": found,
            "inconsistent": inconsistent,
            "not_found": not_found,
        }

        for doc_id in requested_ids:
            db_record = self.get_file_record(doc_id)
            storage_record = storage_records.get(doc_id)
            in_database = _is_db_document(db_record, doc_id)
            in_file_storage = _is_storage_document(storage_record, doc_id)

            if in_database and in_file_storage:
                found.append(doc_id)
                result[str(doc_id)] = {
                    "error_code": 0,
                    "status": SUCCESS,
                    "info": _db_info(self, db_record),
                }
                continue

            if in_database:
                inconsistent.append(doc_id)
                result[str(doc_id)] = {
                    "error_code": 1,
                    "status": MISSING_FILE_STORAGE,
                    "info": _db_info(self, db_record),
                }
            elif in_file_storage:
                inconsistent.append(doc_id)
                result[str(doc_id)] = {
                    "error_code": 1,
                    "status": MISSING_DATABASE,
                    "info": _storage_info(storage_record, storage_records),
                }
            else:
                not_found.append(doc_id)
                result[str(doc_id)] = {
                    "error_code": -1,
                    "status": ABSENT_OR_INVALID,
                }

        return result

    def synchronize_records(
        self,
        all_db_records: list[RecordSchema],
        storage_records: dict[int, RecordSchema],
    ) -> dict:
        remaining_storage = dict(storage_records)

        deleted = 0
        updated = 0
        untouched = len(remaining_storage)

        db_records_to_update: list[RecordSchema] = []
        for db_record in all_db_records:
            if db_record.id not in remaining_storage:
                self.delete_file_record(db_record.id)
                deleted += 1
                continue
            db_records_to_update.append(db_record)

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

    def synchronize(self, store: StorageRecordEntryInterface) -> dict:
        store.ensure_root()
        db_records = self.get_all_records()
        storage_records = store.get_all_records()
        return {**self.synchronize_records(db_records, storage_records),
                "initial DB records": len(db_records), "storage size": len(storage_records)}

    def delete_records(
        self,
        store: StorageRecordEntryInterface,
        record_ids: Iterable[int],
    ) -> tuple[int, int, list[int]]:
        requested_ids = _unique_ids(record_ids)
        target_records = self._get_related_records(requested_ids)
        target_ids = _unique_ids(int(record.id) for record in target_records)
        target_id_set = set(target_ids)
        missing_ids = [record_id for record_id in requested_ids if record_id not in target_id_set]

        deleted_from_storage = 0
        for record_id in target_ids:
            if store.delete_record(record_id):
                deleted_from_storage += 1

        if target_ids:
            self._delete_records(target_ids)

        return len(target_ids), deleted_from_storage, missing_ids


    def put_doc(self, store: StorageRecordEntryInterface, file_uri, data: bytes, *,
                metadata_text: str = "", doc_type: str = "txt") -> dict:
        if file_uri is None and "base64" in doc_type:
            data = base64.b64decode(data)
        data = prepare_doc_data(data)
        document = self.create_file_record(str(file_uri), 0, len(data), 0,
                                           metadata_json={"comment": metadata_text} if metadata_text else {},
                                           doc_type=doc_type)
        stored = store.add_document(file_uri, document.id, data, offset=document.offset,
                                    metadata_text=metadata_text, doc_type=doc_type)
        document.parent_id = stored.id
        self.update_file_record_ext(document.id, document)
        return {"unique_id": stored.id}

    def attach_doc_chunk(self, store: StorageRecordEntryInterface, document_id: int,
                         data: bytes, *, metadata_text: str = "") -> dict:
        parent = self.get_file_record(document_id)
        stored_parent = store.get_record(document_id)
        if parent is None:
            raise ValueError(f"Parent document id={document_id} does not exist in DB")
        if stored_parent is None:
            raise ValueError(f"Parent document id={document_id} does not exist in storage")
        if parent.parent_id != parent.id:
            raise ValueError(f"Record id={document_id} is not a full document")
        if stored_parent.parent_id != stored_parent.id:
            raise ValueError(f"Storage record id={document_id} is not a full document")
        data = prepare_doc_data(data)
        if "base64" in parent.doc_type.split(','):
            data = base64.b64decode(data)
        offset, size = store.get_chunk_bounds(stored_parent, data)
        if parent.size >= 0 and offset + size > parent.size:
            raise ValueError(f"chunk with offset: {offset} and size: {size} does not fit into the parent document of size: {parent.size}, type: {parent.doc_type}")
        chunk = self.create_file_record(parent.file_path, 0, 0, 0,
                                        metadata_json={"comment": metadata_text})
        stored = None
        try:
            stored = store.add_chunk(stored_parent.file_uri, chunk.id, metadata_text=metadata_text)
            store.update_record(chunk.id, parent_id=document_id, offset_size=(offset, size))
            chunk.offset, chunk.size, chunk.parent_id = offset, size, document_id
            self.update_file_record_ext(chunk.id, chunk)
        except Exception:
            if stored is not None:
                store.delete_record(chunk.id)
            self.delete_file_record(chunk.id)
            raise
        return {"unique_id": chunk.id}

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


def _unique_ids(doc_ids: list[int]) -> list[int]:
    return list(dict.fromkeys(doc_ids))

def _is_db_document(record: RecordSchema | None, doc_id: int) -> bool:
    return record is not None and int(record.parent_id) == doc_id

def _is_storage_document(record: RecordSchema | None, doc_id: int) -> bool:
    return record is not None and record.parent_id == doc_id

def _db_info(
    access,
    document: RecordSchema,
) -> dict[str, object]:
    chunks = access._get_chunk_ids(document.id)
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
