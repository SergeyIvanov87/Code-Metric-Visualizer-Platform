"""Database-neutral document schema and record access contract."""

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any, ClassVar, Iterable, TYPE_CHECKING


if TYPE_CHECKING:
    from interfaces import RuntimeConfig


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
    def create_record(self, record: AccessRecord, *, preserve_id: bool = False) -> AccessRecord:
        """Allocate an ID, or preserve it when rebuilding from storage."""

    @abstractmethod
    def get_file_record(self, record_id: int) -> AccessRecord | None:
        """Fetch a single record."""

    @abstractmethod
    def get_all_records(self) -> list[AccessRecord]:
        """Enumerate all records for reconciliation."""

    @abstractmethod
    def update_file_record_ext(self, record_id: int, record: AccessRecord) -> AccessRecord | None:
        """Update path, offset, size, parent, and type, preserving existing metadata."""

    @abstractmethod
    def delete_file_record(self, record_id: int) -> bool:
        """Delete a record and report whether it existed."""

    @abstractmethod
    def get_documents(self, offset: int, limit: int) -> tuple[int, list[AccessRecord]]:
        """Return total document count and a page ordered by ID; -1 is unlimited."""

    def get_records(self, record_ids: Iterable[int]) -> list[AccessRecord]:
        return [record for record_id in dict.fromkeys(record_ids)
                if (record := self.get_file_record(record_id)) is not None]

    def get_chunk_ids(self, document_id: int) -> list[int]:
        return sorted(record.id for record in self.get_all_records()
                      if record.parent_id == document_id and record.id != document_id)

    def get_related_records(self, record_ids: Iterable[int]) -> list[AccessRecord]:
        ids = set(record_ids)
        return [record for record in self.get_all_records()
                if record.id in ids or record.parent_id in ids]

    def delete_records(self, record_ids: Iterable[int]) -> None:
        for record_id in dict.fromkeys(record_ids):
            self.delete_file_record(record_id)

    def create_file_record(self, file_path: str, offset: int, size: int, parent_id: int,
                           metadata_json=None, doc_type: str = "") -> AccessRecord:
        return self.create_record(AccessRecord(file_path=file_path, offset=offset, size=size,
                                  parent_id=parent_id, metadata_json=metadata_json or {},
                                  doc_type=doc_type))

    def create_file_record_with_uid(self, uid: int, file_path: str, offset: int, size: int,
                                    parent_id: int, metadata_json=None, doc_type: str = "") -> AccessRecord:
        return self.create_record(AccessRecord(file_path=file_path, id=uid, offset=offset,
                                  size=size, parent_id=parent_id,
                                  metadata_json=metadata_json or {}, doc_type=doc_type),
                                  preserve_id=True)
