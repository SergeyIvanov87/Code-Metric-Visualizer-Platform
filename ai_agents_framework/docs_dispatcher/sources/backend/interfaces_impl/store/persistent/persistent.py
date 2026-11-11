from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from interfaces import RuntimeConfig
from interfaces.access import AccessRecordEntryInterface
from interfaces.store.utils import canonize_file_uri, decanonize_file_uri
from interfaces.schema import RecordSchema
from interfaces.store import StorageRecordEntryInterface


class PersistentStorageRecordEntry(StorageRecordEntryInterface):
    """Own the naming, creation, reading and sizing of stored document data."""

    doc_suffix = ".storage_bin"

    def init_record_from_path(self, file_uri : str, Path, unique_id: int, *,
                              parent_id: int = 0, offset: int = 0, metadata_text: str = "", doc_type: str = "") -> RecordSchema:
        if not self.exists():
            raise RuntimeError(f"Cannot add the main document: {file_uri}, the storage path doesn't exist: {self.directory}")
        entry = self._entry(unique_id)
        entry.create()
        entry.rename_document(file_uri)
        size = entry.document_size(file_uri)
        entry.write_fields(offset=offset, size=size, parent_id=parent_id,
                           metadata=metadata_text, doc_type=doc_type)

        return RecordSchema(file_uri=file_uri, id=unique_id, offset=offset, size=size,
                             parent_id=parent_id, metadata={"comment": metadata_text} if metadata_text else {},
                             doc_type=doc_type)


    def init_record_from_data(self, file_uri : str | Path | None, Path, unique_id: int, data = bytes, *,
                              parent_id: int = 0,
                              offset: int = 0, metadata_text: str = "", doc_type: str = "") -> RecordSchema:
        if not self.exists():
            raise RuntimeError(f"Cannot add the main document: {file_uri}, the storage path doesn't exist: {self.directory}")
        entry = self._entry(unique_id)
        entry.create()
        size = entry.write_document(file_uri, data)
        entry.write_fields(offset=offset, size=size, parent_id=parent_id,
                           metadata=metadata_text, doc_type=doc_type)

        return RecordSchema(file_uri=file_uri, id=unique_id, offset=offset, size=size,
                             parent_id=parent_id, metadata={"comment": metadata_text} if metadata_text else {},
                             doc_type=doc_type)

    def delete_records(self, record_ids: Iterable[int], cascade_delete: bool = True) -> tuple[int, list[int]]:
        requested_ids = list(dict.fromkeys(record_ids))
        requested_id_set = set(requested_ids)
        records_by_id = {
            int(record.id): record
            for record in self.get_records(requested_ids)
        }
        non_deleted_ids = []
        deleted_parent_ids = set()
        deleted_count = 0

        for record_id in requested_ids:
            record = records_by_id.get(record_id)
            if record is None:
                non_deleted_ids.append(record_id)
                continue

            entry_to_delete = self._entry(record_id)
            try:
                deleted = entry_to_delete.delete()
            except OSError:
                deleted = False

            if not deleted:
                non_deleted_ids.append(record_id)
                continue

            deleted_count += 1
            if record.id == record.parent_id:
                deleted_parent_ids.add(int(record.id))

        if cascade_delete and deleted_parent_ids:
            # Parent records do not contain their child IDs, so scan every
            # numeric record directory and delete chunks of removed parents.
            for directory in self.directory.iterdir():
                if not directory.is_dir() or not directory.name.isdigit():
                    continue

                record_id = int(directory.name)
                # Do not retry requested records that failed to delete.
                if record_id in requested_id_set:
                    continue

                entry = type(self)(directory)
                record = RecordSchema(**entry.read_fields())
                if record.parent_id not in deleted_parent_ids:
                    continue

                try:
                    deleted = entry.delete()
                except OSError:
                    deleted = False

                if deleted:
                    deleted_count += 1
                else:
                    non_deleted_ids.append(record_id)

        return deleted_count, non_deleted_ids


    def get_records(self, record_ids: Iterable[int]) -> list[RecordSchema]:
        entries = [self._entry(unique_id) for unique_id in record_ids ]
        return [RecordSchema(**entry.read_fields()) for entry in entries  if entry.exists()]

    def get_all_records(self) -> dict[int, RecordSchema]:
        records = {}
        for directory in self.directories(self.directory):
            record = RecordSchema(**type(self)(directory).read_fields())
            records[record.id] = record
        return records

    def _get_chunk_ids(self, document_ids: Iterable[int]) -> dict[int, list[int]]:
        requested_ids = _unique_ids(document_ids)
        chunk_ids_by_document = {document_id: [] for document_id in requested_ids}
        if not requested_ids:
            return chunk_ids_by_document

        requested_id_set = set(requested_ids)
        for directory in self.directory.iterdir():
            if not directory.is_dir() or not directory.name.isdigit():
                continue

            parent_id_path = directory / self.parent_id
            if not parent_id_path.is_file():
                continue

            record_id = int(directory.name)
            parent_id = int(parent_id_path.read_text(encoding="utf-8").strip())
            if parent_id in requested_id_set and record_id != parent_id:
                chunk_ids_by_document[parent_id].append(record_id)

        for chunk_ids in chunk_ids_by_document.values():
            chunk_ids.sort()

        return chunk_ids_by_document


    def _entry(self, unique_id: int):
        return type(self)(self.record_path(self.directory, unique_id))

    def rename_document(self, file_uri: str | Path) -> None:
        src_path = Path(file_uri)
        dst_path = self.document_path(file_uri)
        src_path.rename(dst_path)

    def document_size(self, file_uri: str | Path) -> int:
        return self.document_path(file_uri).stat().st_size


    def read_fields(self) -> dict:
        fields = super().read_fields()
        fields["file_uri"] = ""
        for entry in self.directory.iterdir():
            if entry.suffix == self.doc_suffix:
                fields["file_uri"] = decanonize_file_uri(entry.stem)
        return fields


    def read_record_data(self, record: RecordSchema) -> bytes:
        entry = self._entry(record.id)
        return entry.document_path(record.file_uri).read_bytes()

    ####### reconsider the rest
    def document_path(self, file_uri: str | Path) -> Path:
        uri = self.directory / canonize_file_uri(str(file_uri))
        return uri.with_name(f"{uri.name}{self.doc_suffix}")

    def write_document(self, file_uri: str | Path, data: bytes | bytearray) -> int:
        return self.document_path(file_uri).write_bytes(data)

    def create_chunk(self, file_uri: str | Path) -> None:
        self.document_path(file_uri).touch(exist_ok=False)


    @classmethod
    @contextmanager
    def create_instance(cls, config: RuntimeConfig):
        value = config.options.get("storage_uri")
        if not value:
            raise ValueError("Persistent storage requires storage_uri")
        yield cls(Path(value))

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
            payloads[document_id] = self.read_record_data(document)
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
