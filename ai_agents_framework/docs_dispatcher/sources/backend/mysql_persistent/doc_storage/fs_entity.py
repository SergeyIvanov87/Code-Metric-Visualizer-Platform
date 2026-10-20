"""Filesystem entries shared by storage backends and persistent payload handling."""

import shutil
from pathlib import Path

from ..utils import canonize_file_uri


class StorageRecordEntryInterface:
    """Manage record directories and fields independently of document payloads."""

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


class PersistentStorageRecordEntry(StorageRecordEntryInterface):
    """Own the naming, creation, reading and sizing of stored document data."""

    doc_suffix = ".storage_bin"

    def document_path(self, file_uri: str | Path) -> Path:
        uri = self.directory / canonize_file_uri(str(file_uri))
        return uri.with_name(f"{uri.name}{self.doc_suffix}")

    def read_fields(self) -> dict:
        fields = super().read_fields()
        fields["file_uri"] = ""
        for entry in self.directory.iterdir():
            if entry.suffix == self.doc_suffix:
                fields["file_uri"] = entry.stem
        return fields

    def write_document(self, file_uri: str | Path, data: bytes | bytearray) -> None:
        self.document_path(file_uri).write_bytes(data)

    def create_chunk(self, file_uri: str | Path) -> None:
        self.document_path(file_uri).touch(exist_ok=False)

    def read_document(self, file_uri: str | Path) -> bytes:
        return self.document_path(file_uri).read_bytes()

    def document_size(self, file_uri: str | Path) -> int:
        return self.document_path(file_uri).stat().st_size
