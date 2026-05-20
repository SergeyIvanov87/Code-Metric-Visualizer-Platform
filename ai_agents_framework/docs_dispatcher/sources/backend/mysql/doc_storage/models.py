from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

from .fs_entity import StorageRecordEntry


@dataclass
class StorageRecord:
    file_uri: Union[str, Path]
    unique_id: int
    offset: int = -1
    size: int = -1
    parent_id: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_directory(cls, directory: Path) -> "StorageRecord":
        unique_id = int(directory.name)
        file_uri = ""
        parent_id = 0
        offset = -1
        size = -1
        metadata: dict[str, Any] = {}

        for entry in directory.iterdir():
            if entry.suffix == StorageRecordEntry.doc_suffix:
                file_uri = entry.stem
            elif entry.name == StorageRecordEntry.parent_id:
                parent_id = int(entry.read_text().strip())
            elif entry.name == StorageRecordEntry.offset:
                offset = int(entry.read_text().strip())
            elif entry.name == StorageRecordEntry.size:
                size = int(entry.read_text().strip())
            elif entry.name == StorageRecordEntry.metadata:
                raw_metadata = entry.read_text()
                if raw_metadata:
                    metadata = {"comment": raw_metadata}

        return cls(
            file_uri=file_uri,
            unique_id=unique_id,
            offset=offset,
            size=size,
            parent_id=parent_id,
            metadata=metadata,
        )

    @classmethod
    def create_from_path(cls, path: Path) -> "StorageRecord":
        return cls.from_directory(path)

    def commit_doc(self, storage_uri: Path, *, offset: int | None = None):
        doc_entry_path = storage_uri / str(self.unique_id)
        assert doc_entry_path.is_dir(), f"StorageRecord must describe a valid directory: {doc_entry_path}"

        offset_value = 0 if offset is None else offset
        offset_file_path = doc_entry_path / StorageRecordEntry.offset
        with offset_file_path.open(mode="w", encoding="utf-8") as offset_file:
            offset_file.write(str(offset_value))
        self.offset = offset_value

        size_file_path = doc_entry_path / StorageRecordEntry.size
        doc_bin_file_path = (doc_entry_path / self.file_uri).with_suffix(StorageRecordEntry.doc_suffix)
        size_bytes = doc_bin_file_path.stat().st_size
        with size_file_path.open(mode="w", encoding="utf-8") as size_file:
            size_file.write(str(size_bytes))
        self.size = size_bytes

        parent_id_file_path = doc_entry_path / StorageRecordEntry.parent_id
        with parent_id_file_path.open(mode="w", encoding="utf-8") as parent_id_file:
            parent_id_file.write(str(self.unique_id))
        self.parent_id = self.unique_id

    def commit_chunk(
        self,
        storage_uri: Path,
        *,
        metadata_text: str = "",
    ) -> None:
        self._create_placeholder_entry(
            storage_uri,
            metadata_text=metadata_text,
            parent_id=0,
        )

    def update_record(
        self,
        storage_uri: Path,
        *,
        parent_id: int,
        offset_size: tuple[int, int],
    ) -> None:
        offset, size = offset_size
        doc_entry_path = storage_uri / str(self.unique_id)
        assert doc_entry_path.is_dir(), f"StorageRecord must describe a valid directory: {doc_entry_path}"

        offset_file_path = doc_entry_path / StorageRecordEntry.offset
        with offset_file_path.open(mode="w", encoding="utf-8") as offset_file:
            offset_file.write(str(offset))
        self.offset = offset

        size_file_path = doc_entry_path / StorageRecordEntry.size
        with size_file_path.open(mode="w", encoding="utf-8") as size_file:
            size_file.write(str(size))
        self.size = size

        parent_id_file_path = doc_entry_path / StorageRecordEntry.parent_id
        with parent_id_file_path.open(mode="w", encoding="utf-8") as parent_id_file:
            parent_id_file.write(str(parent_id))
        self.parent_id = parent_id

    def update_parent_id(
        self,
        storage_uri: Path,
        parent_id: int,
        *,
        offset_size: tuple[int, int],
    ) -> None:
        self.update_record(
            storage_uri,
            parent_id=parent_id,
            offset_size=offset_size,
        )

    def _create_placeholder_entry(
        self,
        storage_uri: Path,
        *,
        metadata_text: str,
        parent_id: int,
    ) -> None:
        doc_entry_path = storage_uri / str(self.unique_id)
        assert doc_entry_path.is_dir(), f"StorageRecord must describe a valid directory: {doc_entry_path}"

        offset_file_path = doc_entry_path / StorageRecordEntry.offset
        with offset_file_path.open(mode="w", encoding="utf-8") as offset_file:
            offset_file.write("0")
        self.offset = 0

        size_file_path = doc_entry_path / StorageRecordEntry.size
        with size_file_path.open(mode="w", encoding="utf-8") as size_file:
            size_file.write("0")
        self.size = 0

        parent_id_file_path = doc_entry_path / StorageRecordEntry.parent_id
        with parent_id_file_path.open(mode="w", encoding="utf-8") as parent_id_file:
            parent_id_file.write(str(parent_id))
        self.parent_id = parent_id

        metadata_file_path = doc_entry_path / StorageRecordEntry.metadata
        with metadata_file_path.open(mode="w", encoding="utf-8") as metadata_file:
            metadata_file.write(metadata_text)
        self.metadata = {"comment": metadata_text} if metadata_text else {}
