from contextlib import contextmanager
from pathlib import Path
import shutil
from typing import Iterable

from interfaces import RuntimeConfig
from interfaces.store.utils import canonize_file_uri, decanonize_file_uri
from interfaces.schema import RecordSchema
from interfaces.store import StorageRecordEntryInterface


class PersistentStorageRecordEntry(StorageRecordEntryInterface):
    """Own the naming, creation, reading and sizing of stored document data."""

    doc_suffix = ".storage_bin"

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def exists(self) -> bool:
        return self.directory.is_dir()

    def ensure_root(self) -> None:
        self.directory.mkdir(mode=0o777, parents=True, exist_ok=True)

    def create(self) -> None:
        self.directory.mkdir(mode=0o777, parents=True, exist_ok=False)

    def write_fields(self, **fields) -> None:
        self.require_directory()
        for name, value in fields.items():
            path = self.directory / getattr(self, name)
            path.write_text(str(value), encoding="utf-8")

    def require_directory(self) -> None:
        assert self.exists(), (
            "A storage record must describe a valid directory: "
            f"{self.directory}"
        )

    def delete(self) -> bool:
        if not self.directory.exists():
            return False
        shutil.rmtree(self.directory)
        return True

    def _cleanup_incomplete_entry(self, original_error: Exception) -> None:
        try:
            self.delete()
        except OSError as cleanup_error:
            raise RuntimeError(
                f"{original_error}; cleanup of incomplete storage entry "
                f"{self.directory} failed: {cleanup_error}"
            ) from original_error

    def init_record_from_path(self, file_uri: str | Path, unique_id: int, *,
                              parent_id: int = 0, offset: int = 0, metadata_text: str = "", doc_type: str = "") -> RecordSchema:
        if not self.exists():
            raise RuntimeError(f"Cannot add the main document: {file_uri}, the storage path doesn't exist: {self.directory}")
        entry = self._entry(unique_id)
        entry.create()
        try:
            entry.rename_document(file_uri)
            size = entry.document_size(file_uri)
            entry.write_fields(offset=offset, size=size, parent_id=parent_id,
                               metadata=metadata_text, doc_type=doc_type)
        except Exception as error:
            entry._cleanup_incomplete_entry(error)
            raise

        return RecordSchema(file_uri=file_uri, id=unique_id, offset=offset, size=size,
                             parent_id=parent_id, metadata={"comment": metadata_text} if metadata_text else {},
                             doc_type=doc_type)


    def init_record_from_data(self, file_uri: str | Path | None, unique_id: int, data: bytes, *,
                              parent_id: int = 0,
                              offset: int = 0, metadata_text: str = "", doc_type: str = "") -> RecordSchema:
        if not self.exists():
            raise RuntimeError(f"Cannot add the main document: {file_uri}, the storage path doesn't exist: {self.directory}")
        entry = self._entry(unique_id)
        entry.create()
        try:
            size = len(data)
            payload = data if parent_id == unique_id else b""
            entry.write_document(file_uri, payload)
            entry.write_fields(offset=offset, size=size, parent_id=parent_id,
                               metadata=metadata_text, doc_type=doc_type)
        except Exception as error:
            entry._cleanup_incomplete_entry(error)
            raise

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

    @staticmethod
    def record_path(storage_uri: Path, unique_id: int) -> Path:
        return storage_uri / str(unique_id)

    def rename_document(self, file_uri: str | Path) -> None:
        src_path = Path(file_uri)
        dst_path = self.document_path(file_uri)
        src_path.rename(dst_path)

    def document_size(self, file_uri: str | Path) -> int:
        return self.document_path(file_uri).stat().st_size


    def read_fields(self) -> dict:
        fields = {"id": int(self.directory.name)}
        for name, filename in (
            ("parent_id", self.parent_id),
            ("offset", self.offset),
            ("size", self.size),
            ("metadata", self.metadata),
            ("doc_type", self.doc_type),
        ):
            path = self.directory / filename
            if not path.exists():
                continue
            value = path.read_text()
            if name in ("parent_id", "offset", "size"):
                value = int(value.strip())
            elif name == "metadata":
                value = {"comment": value} if value else {}
            fields[name] = value

        fields["file_uri"] = ""
        for entry in self.directory.iterdir():
            if entry.suffix == self.doc_suffix:
                fields["file_uri"] = decanonize_file_uri(entry.stem)
        return fields


    def read_record_data(self, record: RecordSchema) -> bytes:
        entry = self._entry(record.id)
        return entry.document_path(record.file_uri).read_bytes()

    def document_path(self, file_uri: str | Path) -> Path:
        uri = self.directory / canonize_file_uri(str(file_uri))
        return uri.with_name(f"{uri.name}{self.doc_suffix}")

    def write_document(self, file_uri: str | Path, data: bytes | bytearray) -> int:
        return self.document_path(file_uri).write_bytes(data)

    @classmethod
    @contextmanager
    def create_instance(cls, config: RuntimeConfig):
        value = config.options.get("storage_uri")
        if not value:
            raise ValueError("Persistent storage requires storage_uri")
        yield cls(Path(value))

def _unique_ids(record_ids: Iterable[int]) -> list[int]:
    return list(dict.fromkeys(record_ids))
