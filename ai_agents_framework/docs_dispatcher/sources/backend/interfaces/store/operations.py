from pathlib import Path

from .entry import StorageRecordEntryInterface
from .models import StorageRecord, _entry


def get_record_path(storage_uri: Path, unique_id: int) -> Path:
    return StorageRecordEntryInterface.record_path(storage_uri, unique_id)


def get_all_records(uri: Path) -> dict[int, StorageRecord]:
    records: dict[int, StorageRecord] = {}
    for entry in StorageRecordEntryInterface.directories(uri):
        record = StorageRecord.from_directory(entry)
        records[record.unique_id] = record
    return records


def get_record(storage_uri: Path, unique_id: int) -> StorageRecord | None:
    entry = _entry(get_record_path(storage_uri, unique_id))
    if not entry.exists():
        return None
    return StorageRecord.from_directory(entry.directory)


def delete_record(storage_uri: Path, unique_id: int) -> bool:
    return _entry(get_record_path(storage_uri, unique_id)).delete()


def get_records_by_parent_id(storage_uri: Path, parent_id: int) -> dict[int, StorageRecord]:
    return {record_id: record for record_id, record in get_all_records(storage_uri).items()
            if record.parent_id == parent_id}


def add_abstract_document(storage_uri: Path, file_uri: Path, unique_id: int, doc_data: bytearray) -> StorageRecord:
    if not _entry(storage_uri).exists():
        raise RuntimeError(f"Cannot add the main document: {file_uri}, the storage path doesn't exist: {storage_uri}")
    record = StorageRecord(file_uri=file_uri, unique_id=unique_id)
    entry = record.entry(storage_uri)
    entry.create()
    entry.write_document(file_uri, doc_data)
    entry.write_fields(parent_id=unique_id)
    return record


def add_abstract_chunk(
    storage_uri: Path,
    file_uri: Path,
    unique_id: int,
    metadata_text: str,
) -> StorageRecord:
    if not _entry(storage_uri).exists():
        raise RuntimeError(f"Cannot add a chunk: {file_uri}, the storage path doesn't exist: {storage_uri}")
    record = StorageRecord(file_uri=file_uri, unique_id=unique_id)
    entry = record.entry(storage_uri)
    entry.create()
    entry.create_chunk(file_uri)
    record.commit_chunk(storage_uri, metadata_text=metadata_text)
    return record
