from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from interfaces import RuntimeConfig
from interfaces.access import AccessRecordEntryInterface
from interfaces.access.utils import canonize_file_uri
from interfaces.schema import RecordSchema
from interfaces.store import StorageRecordEntryInterface


class PersistentStorageRecordEntry(StorageRecordEntryInterface):
    """Own the naming, creation, reading and sizing of stored document data."""

    doc_suffix = ".storage_bin"

    def document_path(self, file_uri: str | Path) -> Path:
        uri = self.directory / canonize_file_uri(str(file_uri))
        return uri.with_name(f"{uri.name}{self.doc_suffix}")

    def read_fields(self) -> dict:
        fields = super().read_fields()
        fields["file_uri"] = ""
        for entry in self.directory.iterdir():
            if entry.suffix == self.doc_suffix:
                fields["file_uri"] = entry.stem
        return fields

    def write_document(self, file_uri: str | Path, data: bytes | bytearray) -> None:
        self.document_path(file_uri).write_bytes(data)

    def create_chunk(self, file_uri: str | Path) -> None:
        self.document_path(file_uri).touch(exist_ok=False)

    def read_document(self, file_uri: str | Path) -> bytes:
        return self.document_path(file_uri).read_bytes()

    def document_size(self, file_uri: str | Path) -> int:
        return self.document_path(file_uri).stat().st_size

    @classmethod
    @contextmanager
    def create_instance(cls, config: RuntimeConfig):
        value = config.options.get("storage_uri")
        if not value:
            raise ValueError("Persistent storage requires storage_uri")
        yield cls(Path(value))

    def _entry(self, unique_id: int):
        return type(self)(self.record_path(self.directory, unique_id))

    def get_all_records(self) -> dict[int, RecordSchema]:
        records = {}
        for directory in self.directories(self.directory):
            record = RecordSchema(**type(self)(directory).read_fields())
            records[record.id] = record
        return records

    def get_record(self, unique_id: int) -> RecordSchema | None:
        entry = self._entry(unique_id)
        return RecordSchema(**entry.read_fields()) if entry.exists() else None

    def delete_record(self, unique_id: int) -> bool:
        return self._entry(unique_id).delete()

    def add_document(self, file_uri: str | Path, unique_id: int, data: bytes, *,
                     offset: int = 0, metadata_text: str = "", doc_type: str = "") -> RecordSchema:
        if not self.exists():
            raise RuntimeError(f"Cannot add the main document: {file_uri}, the storage path doesn't exist: {self.directory}")
        entry = self._entry(unique_id)
        entry.create()
        entry.write_document(file_uri, data)
        size = entry.document_size(file_uri)
        entry.write_fields(offset=offset, size=size, parent_id=unique_id,
                           metadata=metadata_text, doc_type=doc_type)
        return RecordSchema(file_uri=file_uri, id=unique_id, offset=offset, size=size,
                             parent_id=unique_id, metadata={"comment": metadata_text} if metadata_text else {},
                             doc_type=doc_type)

    def add_chunk(self, file_uri: str | Path, unique_id: int, *, metadata_text: str = "") -> RecordSchema:
        if not self.exists():
            raise RuntimeError(f"Cannot add a chunk: {file_uri}, the storage path doesn't exist: {self.directory}")
        entry = self._entry(unique_id)
        entry.create()
        entry.create_chunk(file_uri)
        entry.write_fields(offset=0, size=0, parent_id=0, metadata=metadata_text)
        return RecordSchema(file_uri=file_uri, id=unique_id, offset=0, size=0,
                             metadata={"comment": metadata_text} if metadata_text else {})

    def update_record(self, unique_id: int, *, parent_id: int, offset_size: tuple[int, int]) -> None:
        offset, size = offset_size
        self._entry(unique_id).write_fields(offset=offset, size=size, parent_id=parent_id)

    def get_chunk_bounds(self, document: RecordSchema, data: bytes) -> tuple[int, int]:
        parent_data = self._entry(document.id).read_document(document.file_uri)
        offset = parent_data.find(data)
        if offset < 0:
            raise ValueError("chunk does not belong to the parent document")
        return offset, len(data)

    def read_ids(
        self,
        access: AccessRecordEntryInterface,
        record_ids: Iterable[int],
    ) -> dict[int, dict[str, object]]:
        requested_ids = _unique_ids(record_ids)
        storage_records = self.get_all_records()
        resolved, resolution_errors = _resolve_records(
            access,
            storage_records,
            requested_ids,
        )
        payloads, payload_errors = _read_document_payloads(
            self,
            storage_records,
            (record.document_id for record in resolved.values()),
        )
        results = _extract_contexts(resolved, payloads, payload_errors)

        for record_id, error_msg in resolution_errors.items():
            results[record_id] = {
                "id": record_id,
                "error_code": -1,
                "status": "error",
                "error_msg": error_msg,
            }

        return {record_id: results[record_id] for record_id in requested_ids}


@dataclass(frozen=True)
class ResolvedRecord:
    record_id: int
    parent_id: int
    offset: int
    size: int

    @property
    def record_type(self) -> str:
        return "document" if self.parent_id == self.record_id else "chunk"

    @property
    def document_id(self) -> int:
        return self.record_id if self.record_type == "document" else self.parent_id

def _unique_ids(record_ids: Iterable[int]) -> list[int]:
    return list(dict.fromkeys(record_ids))

def _record_fields(record: RecordSchema) -> tuple[int, int, int]:
    return int(record.parent_id), int(record.offset), int(record.size)

def _resolve_records(
    access: AccessRecordEntryInterface,
    storage_records: dict[int, RecordSchema],
    record_ids: Iterable[int],
) -> tuple[dict[int, ResolvedRecord], dict[int, str]]:
    requested_ids = _unique_ids(record_ids)
    db_records = {int(record.id): record for record in access.get_records(requested_ids)}
    resolved: dict[int, ResolvedRecord] = {}
    errors: dict[int, str] = {}

    for record_id in requested_ids:
        db_record = db_records.get(record_id)
        storage_record = storage_records.get(record_id)
        if db_record is None and storage_record is None:
            errors[record_id] = f"Record id={record_id} does not exist"
            continue

        if db_record is not None and storage_record is not None:
            db_fields = _record_fields(db_record)
            storage_fields = _record_fields(storage_record)
            db_parent_id, db_offset, db_size = db_fields
            storage_parent_id, storage_offset, storage_size = storage_fields
            if db_parent_id != storage_parent_id:
                errors[record_id] = (
                    f"Record id={record_id} has inconsistent parent_id between DB "
                    "and file storage"
                )
                continue
            is_chunk = db_parent_id != record_id
            if is_chunk and (db_offset, db_size) != (storage_offset, storage_size):
                errors[record_id] = (
                    f"Chunk id={record_id} has inconsistent offset or size between DB "
                    "and file storage"
                )
                continue
            parent_id, offset, size = db_fields
        elif db_record is not None:
            parent_id, offset, size = _record_fields(db_record)
        else:
            parent_id, offset, size = _record_fields(storage_record)

        resolved[record_id] = ResolvedRecord(
            record_id=record_id,
            parent_id=parent_id,
            offset=offset,
            size=size,
        )

    return resolved, errors

def _read_document_payloads(
    store: StorageRecordEntryInterface,
    storage_records: dict[int, RecordSchema],
    document_ids: Iterable[int],
) -> tuple[dict[int, bytes], dict[int, str]]:
    payloads: dict[int, bytes] = {}
    errors: dict[int, str] = {}

    for document_id in _unique_ids(document_ids):
        document = storage_records.get(document_id)
        if document is None:
            errors[document_id] = (
                f"Parent document id={document_id} does not exist in file storage"
            )
            continue
        if document.parent_id != document.id:
            errors[document_id] = (
                f"Parent id={document_id} does not identify a full document in file storage"
            )
            continue

        try:
            payloads[document_id] = store._entry(document.id).read_document(document.file_uri)
        except OSError as exc:
            errors[document_id] = (
                f"Cannot read parent document id={document_id} from file storage: {exc}"
            )

    return payloads, errors

def _extract_contexts(
    records: dict[int, ResolvedRecord],
    payloads: dict[int, bytes],
    payload_errors: dict[int, str],
) -> dict[int, dict[str, object]]:
    results: dict[int, dict[str, object]] = {}

    for record_id, record in records.items():
        payload_error = payload_errors.get(record.document_id)
        if payload_error is not None:
            results[record_id] = {
                "id": record_id,
                "error_code": -1,
                "status": "error",
                "error_msg": payload_error,
            }
            continue

        document_data = payloads[record.document_id]
        if record.record_type == "document":
            context_data = document_data
        else:
            if record.offset < 0 or record.size < 0:
                results[record_id] = {
                    "id": record_id,
                    "error_code": -1,
                    "status": "error",
                    "error_msg": (
                        f"Chunk id={record_id} has invalid offset={record.offset} "
                        f"or size={record.size}"
                    ),
                }
                continue
            chunk_end = record.offset + record.size
            if chunk_end > len(document_data):
                results[record_id] = {
                    "id": record_id,
                    "error_code": -1,
                    "status": "error",
                    "error_msg": (
                        f"Chunk id={record_id} range [{record.offset}, {chunk_end}) "
                        f"exceeds parent document size {len(document_data)}"
                    ),
                }
                continue
            context_data = document_data[record.offset:chunk_end]

        try:
            context = context_data.decode("utf-8")
        except UnicodeDecodeError as exc:
            results[record_id] = {
                "id": record_id,
                "error_code": -1,
                "status": "error",
                "error_msg": f"Record id={record_id} does not contain valid UTF-8 text: {exc}",
            }
            continue

        results[record_id] = {
            "id": record_id,
            "parent_id": record.parent_id,
            "record_type": record.record_type,
            "context": context,
            "error_code": 0,
            "status": "success",
        }

    return results
