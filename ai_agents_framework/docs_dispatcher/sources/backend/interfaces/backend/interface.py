"""Contract for configured backend compositions."""

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING

from interfaces.access import AccessRecordEntryInterface
from interfaces.store import StorageRecordEntryInterface
from interfaces.schema import RecordSchema

if TYPE_CHECKING:
    from interfaces import RuntimeConfig


class Backend(ABC):
    """Own a configured access and storage composition."""

    access: AccessRecordEntryInterface
    store: StorageRecordEntryInterface

    @classmethod
    @abstractmethod
    def create_instance(cls, config: "RuntimeConfig") -> AbstractContextManager["Backend"]:
        """Create a configured backend and own its component lifecycles."""

    @abstractmethod
    def put_doc_by_uri(self, file_uri: str | Path, metadata_text: str = "", doc_type: str = "txt") -> dict:
        """Allocate a document ID and store a complete document."""

    @abstractmethod
    def put_doc_by_data(self, file_uri: str | Path | None, data: bytes, *, metadata_text: str = "", doc_type: str = "txt") -> dict:
        """Allocate a document ID and store a complete document."""

    @abstractmethod
    def attach_doc_chunk(self, document_id: int, data: bytes, *, metadata_text: str = "") -> dict:
        """Validate and attach a chunk, rolling back failed creation."""

    @abstractmethod
    def get_documents(self, offset: int = 0, limit: int = -1) -> dict:
        """List documents with chunk IDs and pagination metadata."""

    @abstractmethod
    def get_document_info(self, doc_ids: list[int]) -> dict:
        """Report complete, inconsistent, and absent documents."""

    @abstractmethod
    def delete_records(self, record_ids: Iterable[int]) -> tuple[int, int, list[int]]:
        """Delete documents and their chunks from both interfaces."""

    @abstractmethod
    def read_ids(self, record_ids: Iterable[int]) -> dict[int, dict[str, object]]:
        """Resolve record consistency and retrieve document or chunk content."""

    @abstractmethod
    def synchronize(self) -> dict:
        """Reconcile access metadata from the selected store."""
