from pathlib import Path

from interfaces.access.utils import canonize_file_uri
from interfaces.store.entry import StorageRecordEntryInterface


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
