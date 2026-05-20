import shutil
from pathlib import Path

from .models import StorageRecord
from .fs_entity import StorageRecordEntry


def get_record_path(storage_uri: Path, unique_id: int) -> Path:
    return storage_uri / str(unique_id)


def get_all_records(uri: Path) -> dict[int, StorageRecord]:
    records: dict[int, StorageRecord] = {}

    for entry in uri.iterdir():
        if not entry.is_dir():
            continue
        record = StorageRecord.from_directory(entry)
        records[record.unique_id] = record

    return records


def get_record(storage_uri: Path, unique_id: int) -> StorageRecord | None:
    record_path = get_record_path(storage_uri, unique_id)
    if not record_path.exists() or not record_path.is_dir():
        return None
    return StorageRecord.from_directory(record_path)


def delete_record(storage_uri: Path, unique_id: int) -> bool:
    record_path = get_record_path(storage_uri, unique_id)
    if not record_path.exists():
        return False

    shutil.rmtree(record_path)
    return True


def get_records_by_parent_id(storage_uri: Path, parent_id: int) -> dict[int, StorageRecord]:
    all_records = get_all_records(storage_uri)
    return {
        record_id: record
        for record_id, record in all_records.items()
        if record.parent_id == parent_id
    }


def add_abstract_document(storage_uri: Path, file_uri: Path, unique_id: int, doc_data: bytearray) -> StorageRecord:
    if not storage_uri.exists():
        storage_uri.mkdir(parents=True, exist_ok=True)

    if not storage_uri.is_dir():
        raise RuntimeError(f"Cannot add the main document: {file_uri}, the storage path doesn't exist: {storage_uri}")

    storage_entry_path = storage_uri / str(unique_id)
    storage_entry_path.mkdir(parents=True, exist_ok=False)

    doc_file_path = (storage_entry_path / file_uri).with_suffix(StorageRecordEntry.doc_suffix)
    with doc_file_path.open(mode='wb') as doc_file:
        doc_file.write(doc_data)


    parent_id_file_path = storage_entry_path / StorageRecordEntry.parent_id
    with parent_id_file_path.open(mode = 'w', encoding = 'utf-8') as parent_id_file:
        parent_id_file.write(str(unique_id))

    return StorageRecord(file_uri = file_uri, unique_id = unique_id)


def add_abstract_chunk(
    storage_uri: Path,
    file_uri: Path,
    unique_id: int,
    metadata_text: str,
) -> StorageRecord:
    if not storage_uri.exists():
        storage_uri.mkdir(parents=True, exist_ok=True)

    if not storage_uri.is_dir():
        raise RuntimeError(
            f"Cannot add a chunk: {file_uri}, the storage path doesn't exist: {storage_uri}"
        )

    storage_entry_path = storage_uri / str(unique_id)
    storage_entry_path.mkdir(parents=True, exist_ok=False)

    chunk_file_path = (storage_entry_path / file_uri).with_suffix(StorageRecordEntry.doc_suffix)
    chunk_file_path.touch(exist_ok=False)

    parent_id_file_path = storage_entry_path / StorageRecordEntry.parent_id
    with parent_id_file_path.open(mode="w", encoding="utf-8") as parent_id_file:
        parent_id_file.write("0")

    offset_file_path = storage_entry_path / StorageRecordEntry.offset
    with offset_file_path.open(mode="w", encoding="utf-8") as offset_file:
        offset_file.write("0")

    size_file_path = storage_entry_path / StorageRecordEntry.size
    with size_file_path.open(mode="w", encoding="utf-8") as size_file:
        size_file.write("0")

    metadata_file_path = storage_entry_path / StorageRecordEntry.metadata
    with metadata_file_path.open(mode="w", encoding="utf-8") as metadata_file:
        metadata_file.write(metadata_text)

    return StorageRecord(
        file_uri=file_uri,
        unique_id=unique_id,
        offset=0,
        size=0,
        parent_id=0,
        metadata={"comment": metadata_text} if metadata_text else {},
    )
