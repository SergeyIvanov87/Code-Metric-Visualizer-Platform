"""Database-neutral record access contract."""

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from pathlib import Path
from typing import ClassVar, Iterable, Mapping, TYPE_CHECKING

from interfaces.schema import RecordSchema


if TYPE_CHECKING:
    from interfaces import RuntimeConfig
    from interfaces.store import StorageRecordEntryInterface


class AccessRecordEntryInterface(ABC):
    """Semantic record operations; no SQL, ORM, engine, or cursor in the API."""

    record_schema: ClassVar[type[RecordSchema]] = RecordSchema

    @classmethod
    @abstractmethod
    def create_instance(cls, config: "RuntimeConfig") -> AbstractContextManager["AccessRecordEntryInterface"]:
        """Create a configured access context and own its connection lifecycle."""

    @abstractmethod
    def create_unique_ids(self, count: int = 1) -> Iterable[int]:
        """Reserve database-generated record IDs using placeholder records."""

    @abstractmethod
    def create_records_by_ids(
        self,
        records_by_id: Mapping[int, RecordSchema],
    ) -> int:
        """Create records with explicit IDs and return the created count."""

    @abstractmethod
    def update_record_by_id(self, unique_id: int, record: RecordSchema) -> int:
        """Update one allocated record; return 1 when found, otherwise 0."""

    @abstractmethod
    def update_records_by_ids(self, records_by_id: Mapping[int, RecordSchema]) -> int:
        """Update found records in one transaction and return the matched count."""

    @abstractmethod
    def get_records(self, record_ids: Iterable[int]) -> list[RecordSchema]:
        """Read records needed to resolve document and chunk content."""

    @abstractmethod
    def get_all_records(self) -> list[RecordSchema]:
        """Read every document and chunk record."""

    @abstractmethod
    def delete_records(self, record_ids: Iterable[int], cascade_delete: bool = True) -> tuple[int, list[int]]:
        """ Delete documents and their chunks. Returns [number ids to delete, list of non deleted ids]
            cascade_delete if enabled, reap the orphant nodes as well if a parent node was deleted
        """

    @abstractmethod
    def document_page(self, offset: int, limit: int) -> tuple[int, list[RecordSchema]]:
        """ Returns slice of the entire documents list starting from `ofset`
            and including no more than `limit`
        """
