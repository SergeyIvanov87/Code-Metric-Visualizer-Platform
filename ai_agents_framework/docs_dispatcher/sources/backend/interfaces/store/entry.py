"""Filesystem entries shared by storage backends and persistent payload handling."""

from dataclasses import dataclass, field
from typing import Any, ClassVar
import shutil
from pathlib import Path

from abc import ABC, abstractmethod


@dataclass
class StorageRecordSchema:
    """Logical storage schema, independent of payload persistence policy."""

    file_uri: str | Path
    unique_id: int
    offset: int = -1
    size: int = -1
    parent_id: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    doc_type: str = ""


class StorageRecordEntryInterface(ABC):
    """Manage record directories and fields independently of document payloads."""

    record_schema: ClassVar[type[StorageRecordSchema]] = StorageRecordSchema

    parent_id = "parentId"
    offset = "offset"
    size = "size"
    metadata = "metadata"
    doc_type = "doc_type"

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    @staticmethod
    def record_path(storage_uri: Path, unique_id: int) -> Path:
        return storage_uri / str(unique_id)

    @staticmethod
    def directories(storage_uri: Path):
        return (entry for entry in storage_uri.iterdir() if entry.is_dir())

    def exists(self) -> bool:
        return self.directory.is_dir()

    def ensure_root(self) -> None:
        self.directory.mkdir(mode=0o777, parents=True, exist_ok=True)

    def create(self) -> None:
        self.directory.mkdir(mode=0o777, parents=True, exist_ok=False)

    def delete(self) -> bool:
        if not self.directory.exists():
            return False
        shutil.rmtree(self.directory)
        return True

    def require_directory(self) -> None:
        assert self.exists(), f"StorageRecord must describe a valid directory: {self.directory}"

    def read_fields(self) -> dict:
        fields = {"unique_id": int(self.directory.name)}
        for name, filename in (("parent_id", self.parent_id), ("offset", self.offset),
                               ("size", self.size), ("metadata", self.metadata),
                               ("doc_type", self.doc_type)):
            path = self.directory / filename
            if not path.exists():
                continue
            value = path.read_text()
            if name in ("parent_id", "offset", "size"):
                value = int(value.strip())
            elif name == "metadata":
                value = {"comment": value} if value else {}
            fields[name] = value
        return fields

    def write_fields(self, **fields) -> None:
        self.require_directory()
        for name, value in fields.items():
            (self.directory / getattr(self, name)).write_text(str(value), encoding="utf-8")

    @abstractmethod
    def document_path(self, file_uri: str | Path) -> Path:
        """Return the backend-specific document location."""

    @abstractmethod
    def write_document(self, file_uri: str | Path, data: bytes | bytearray) -> None:
        """Store document content according to the selected persistence policy."""

    @abstractmethod
    def create_chunk(self, file_uri: str | Path) -> None:
        """Create the backend-specific chunk entry."""

    @abstractmethod
    def read_document(self, file_uri: str | Path) -> bytes:
        """Read document content using the selected persistence policy."""

    @abstractmethod
    def document_size(self, file_uri: str | Path) -> int:
        """Return the document size in bytes."""
