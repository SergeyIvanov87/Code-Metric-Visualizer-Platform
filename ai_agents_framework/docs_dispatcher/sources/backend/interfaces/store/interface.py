"""Storage contract and shared filesystem record utilities."""

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from pathlib import Path
import shutil
from typing import ClassVar, Iterable, TYPE_CHECKING

from interfaces.schema import RecordSchema


if TYPE_CHECKING:
    from interfaces import RuntimeConfig
    from interfaces.access import AccessRecordEntryInterface


class StorageRecordEntryInterface(ABC):
    """Manage record directories and fields independently of document payloads."""

    record_schema: ClassVar[type[RecordSchema]] = RecordSchema

    parent_id = "parentId"
    offset = "offset"
    size = "size"
    metadata = "metadata"
    doc_type = "doc_type"

    def __init__(self, directory: Path):
        self.directory = Path(directory)


    @abstractmethod
    def init_record_from_path(self, file_uri : str, Path, unique_id: int, *,
                              parent_id: int = 0,
                              offset: int = 0, metadata_text: str = "", doc_type: str = "") -> RecordSchema:
        """Create a full document and its metadata."""

    @abstractmethod
    def init_record_from_data(self, file_uri : str | Path | None, Path, unique_id: int, data = bytes, *,
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

    def write_fields(self, **fields) -> None:
        self.require_directory()
        # Codex TODO: don't create a separate file for the name, put them all into a single JSON or YAML file
        for name, value in fields.items():
            (self.directory / getattr(self, name)).write_text(str(value), encoding="utf-8")

    def require_directory(self) -> None:
        assert self.exists(), f"A storage record must describe a valid directory: {self.directory}"

    def read_fields(self) -> dict:
        fields = {"id": int(self.directory.name)}
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

    ############# the rest must be reconsidered
    def delete(self) -> bool:
        if not self.directory.exists():
            return False
        shutil.rmtree(self.directory)
        return True




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
    def document_size(self, file_uri: str | Path) -> int:
        """Return the document size in bytes."""

    @classmethod
    @abstractmethod
    def create_instance(cls, config: "RuntimeConfig") -> AbstractContextManager["StorageRecordEntryInterface"]:
        """Create a configured store context from backend-specific runtime options."""

    @abstractmethod
    def add_document(self, file_uri, unique_id: int, data: bytes, *,
                     offset: int = 0, metadata_text: str = "", doc_type: str = "") -> RecordSchema:
        """Create a full document and its metadata."""

    @abstractmethod
    def add_chunk(self, file_uri, unique_id: int, *, metadata_text: str = "") -> RecordSchema:
        """Create a chunk placeholder and its metadata."""

    @abstractmethod
    def update_record(self, unique_id: int, *, parent_id: int, offset_size: tuple[int, int]) -> None:
        """Set a chunk's parent and byte range."""
