from dataclasses import dataclass
from pathlib import Path

from .entry import StorageRecordEntryInterface, StorageRecordSchema


def _entry(directory: Path) -> StorageRecordEntryInterface:
    # Resolve through the composition; common storage code knows no implementation.
    from dispatcher.runtime import get_backend
    return get_backend().store(directory)


@dataclass
class StorageRecord(StorageRecordSchema):
    @staticmethod
    def canonize_file_uri(doc_dir_uri: Path, file_uri: Path):
        return _entry(doc_dir_uri).document_path(file_uri)

    @staticmethod
    def decanonize_file_uri(uri: Path):
        return uri

    def entry(self, storage_uri: Path) -> StorageRecordEntryInterface:
        return _entry(
            StorageRecordEntryInterface.record_path(storage_uri, self.unique_id)
        )

    @classmethod
    def from_directory(cls, directory: Path) -> "StorageRecord":
        return cls(**_entry(directory).read_fields())

    @classmethod
    def create_from_path(cls, path: Path) -> "StorageRecord":
        return cls.from_directory(path)

    def commit_doc(
        self,
        storage_uri: Path,
        *,
        offset: int | None = None,
        metadata_text: str = "",
        doc_type: str = "",
    ):
        entry = self.entry(storage_uri)
        entry.require_directory()
        offset_value = 0 if offset is None else offset
        size_bytes = entry.document_size(self.file_uri)
        entry.write_fields(offset=offset_value, size=size_bytes, parent_id=self.unique_id,
                           metadata=metadata_text, doc_type=doc_type)
        self.offset = offset_value
        self.size = size_bytes
        self.parent_id = self.unique_id
        self.metadata = {"comment": metadata_text} if metadata_text else {}
        self.doc_type = doc_type

    def commit_chunk(self, storage_uri: Path, *, metadata_text: str = "") -> None:
        self._create_placeholder_entry(storage_uri, metadata_text=metadata_text, parent_id=0)

    def update_record(
        self,
        storage_uri: Path,
        *,
        parent_id: int,
        offset_size: tuple[int, int],
    ) -> None:
        offset, size = offset_size
        self.entry(storage_uri).write_fields(offset=offset, size=size, parent_id=parent_id)
        self.offset = offset
        self.size = size
        self.parent_id = parent_id

    def update_parent_id(
        self,
        storage_uri: Path,
        parent_id: int,
        *,
        offset_size: tuple[int, int],
    ) -> None:
        self.update_record(storage_uri, parent_id=parent_id, offset_size=offset_size)

    def _create_placeholder_entry(
        self,
        storage_uri: Path,
        *,
        metadata_text: str,
        parent_id: int,
    ) -> None:
        self.entry(storage_uri).write_fields(offset=0, size=0, parent_id=parent_id,
                                            metadata=metadata_text)
        self.offset = 0
        self.size = 0
        self.parent_id = parent_id
        self.metadata = {"comment": metadata_text} if metadata_text else {}
