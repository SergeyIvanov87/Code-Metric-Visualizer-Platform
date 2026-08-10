from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import FileRecord

_SYNC_FIELDS = ("file_path", "offset", "size", "parent_id")


def create_file_record(
    db: Session,
    file_path: str,
    offset: int,
    size: int,
    parent_id: int,
    metadata_json: Optional[dict[str, Any]] = None,
) -> FileRecord:

    file_path = str(file_path).replace('/', '_')
    record = FileRecord(
        file_path=file_path,
        offset=offset,
        size=size,
        parent_id=parent_id,
        metadata_json=metadata_json,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def create_file_record_with_uid(
    db: Session,
    uid: int,
    file_path: str,
    offset: int,
    size: int,
    parent_id: int,
    metadata_json: Optional[dict[str, Any]] = None,
) -> FileRecord:
    existing = db.query(FileRecord).filter(FileRecord.id == uid).first()
    if existing:
        raise ValueError(f"Record with id={uid} already exists")

    file_path = str(file_path).replace('/', '_')
    record = FileRecord(
        id=uid,
        file_path=file_path,
        offset=offset,
        size=size,
        parent_id=parent_id,
        metadata_json=metadata_json,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def create_file_record_ext(db: Session, record: FileRecord) -> FileRecord:
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_file_record(db: Session, record_id: int) -> Optional[FileRecord]:
    return db.query(FileRecord).filter(FileRecord.id == record_id).first()


def get_all_records(db: Session) -> list[FileRecord]:
    return db.query(FileRecord).all()


def execute_query(db: Session, query_str: str):
    result = db.execute(text(query_str))
    normalized = query_str.lstrip().lower()
    if not normalized.startswith("select"):
        db.commit()
    return result


def update_file_record(
    db: Session,
    record_id: int,
    *,
    file_path: Optional[str] = None,
    offset: Optional[int] = None,
    size: Optional[int] = None,
    parent_id: Optional[int] = None,
    metadata_json: Optional[dict[str, Any]] = None,
) -> Optional[FileRecord]:
    record = get_file_record(db, record_id)
    if not record:
        return None

    if file_path is not None:
        file_path = str(file_path).replace('/', '_')
        record.file_path = file_path
    if offset is not None:
        record.offset = offset
    if size is not None:
        record.size = size
    if parent_id is not None:
        record.parent_id = parent_id
    if metadata_json is not None:
        record.metadata_json = metadata_json

    db.commit()
    db.refresh(record)
    return record


def update_file_record_ext(
    db: Session,
    record_id: int,
    new_record: FileRecord,
) -> Optional[FileRecord]:
    record = get_file_record(db, record_id)
    if not record:
        return None

    for field in _SYNC_FIELDS:
        setattr(record, field, getattr(new_record, field))

    db.commit()
    db.refresh(record)
    return record


def delete_file_record(db: Session, record_id: int) -> bool:
    record = get_file_record(db, record_id)
    if not record:
        return False

    db.delete(record)
    db.commit()
    return True
