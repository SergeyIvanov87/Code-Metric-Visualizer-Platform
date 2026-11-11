"""Storage contract and static path helpers."""

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from pathlib import Path
from typing import ClassVar, Iterable, TYPE_CHECKING

from interfaces.schema import RecordSchema


if TYPE_CHECKING:
    from interfaces import RuntimeConfig


class StorageRecordEntryInterface(ABC):
    """Define backend-neutral storage operations."""

    record_schema: ClassVar[type[RecordSchema]] = RecordSchema
    directory: Path

    parent_id = "parentId"
    offset = "offset"
    size = "size"
    metadata = "metadata"
    doc_type = "doc_type"

    @abstractmethod
    def init_record_from_path(self, file_uri: str | Path, unique_id: int, *,
                              parent_id: int = 0,
                              offset: int = 0, metadata_text: str = "", doc_type: str = "") -> RecordSchema:
        """Create a full document and its metadata."""

    @abstractmethod
    def init_record_from_data(self, file_uri: str | Path | None, unique_id: int, data: bytes, *,
                              parent_id: int = 0,
                              offset: int = 0, metadata_text: str = "", doc_type: str = "") -> RecordSchema:
        """Create a full document and its metadata."""

    @abstractmethod
    def delete_records(self, record_ids: Iterable[int], cascade_delete: bool = True) -> tuple[int, list[int]]:
        """Delete documents and their chunks. Returns [number ids to delete, list of non deleted ids]
            cascade_delete if enabled, reap the orphant nodes as well if a parent node was deleted
        """

    @abstractmethod
    def get_records(self, record_ids: Iterable[int]) -> list[RecordSchema]:
        """Read records needed to resolve document and chunk content."""

    @abstractmethod
    def get_all_records(self) -> dict[int, RecordSchema]:
        """Read every stored document and chunk record by ID."""

    @abstractmethod
    def read_record_data(self, record: RecordSchema) -> bytes:
        """Read document content using the selected persistence policy."""

    @abstractmethod
    def ensure_root(self) -> None:
        """Create the storage root when it does not exist."""

    @classmethod
    @abstractmethod
    def create_instance(cls, config: "RuntimeConfig") -> AbstractContextManager["StorageRecordEntryInterface"]:
        """Create a configured store context from backend-specific runtime options."""

    @abstractmethod
    def document_path(self, file_uri: str | Path) -> Path:
        """Return the backend-specific document location."""

    @abstractmethod
    def write_document(self, file_uri: str | Path, data: bytes | bytearray) -> int:
        """Store document content and return its byte count."""

    @abstractmethod
    def document_size(self, file_uri: str | Path) -> int:
        """Return the document size in bytes."""

    @staticmethod
    def record_path(storage_uri: Path, unique_id: int) -> Path:
        return storage_uri / str(unique_id)

    @staticmethod
    def directories(storage_uri: Path):
        return (entry for entry in storage_uri.iterdir() if entry.is_dir())
