"""Database-neutral document schema and record access contract."""

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Iterable, TYPE_CHECKING


if TYPE_CHECKING:
    from interfaces import RuntimeConfig
    from interfaces.store import StorageRecordEntryInterface


@dataclass
class AccessRecord:
    """Logical schema shared by SQL and NoSQL access implementations.

    IDs are allocated by the access implementation; parent_id == id identifies
    a full document, and chunks use byte offsets into their parent document.
    """

    file_path: str
    id: int | None = None
    offset: int = -1
    size: int = -1
    parent_id: int = 0
    metadata_json: dict[str, Any] | None = field(default_factory=dict)
    doc_type: str = ""


class AccessRecordEntryInterface(ABC):
    """Semantic record operations; no SQL, ORM, engine, or cursor in the API."""

    record_schema: ClassVar[type[AccessRecord]] = AccessRecord

    @classmethod
    @abstractmethod
    def open(cls, config: "RuntimeConfig") -> AbstractContextManager["AccessRecordEntryInterface"]:
        """Open a configured access context and own its connection lifecycle."""

    @abstractmethod
    def get_records(self, record_ids: Iterable[int]) -> list[AccessRecord]:
        """Read records needed to resolve document and chunk content."""

    @abstractmethod
    def put_doc(self, store: "StorageRecordEntryInterface", file_uri: str | Path | None, data: bytes, *, metadata_text: str = "", doc_type: str = "txt") -> dict:
        """Allocate a document ID and store a complete document."""

    @abstractmethod
    def attach_doc_chunk(self, store: "StorageRecordEntryInterface", document_id: int, data: bytes, *, metadata_text: str = "") -> dict:
        """Validate and attach a chunk, rolling back failed creation."""

    @abstractmethod
    def get_documents(self, offset: int = 0, limit: int = -1) -> dict:
        """List documents with chunk IDs and pagination metadata."""

    @abstractmethod
    def get_document_info(self, store: "StorageRecordEntryInterface", doc_ids: list[int]) -> dict:
        """Report complete, inconsistent, and absent documents."""

    @abstractmethod
    def delete_records(self, store: "StorageRecordEntryInterface", record_ids: Iterable[int]) -> tuple[int, int, list[int]]:
        """Delete documents and their chunks from both interfaces."""

    @abstractmethod
    def synchronize(self, store: "StorageRecordEntryInterface") -> dict:
        """Reconcile access metadata from the selected store."""
