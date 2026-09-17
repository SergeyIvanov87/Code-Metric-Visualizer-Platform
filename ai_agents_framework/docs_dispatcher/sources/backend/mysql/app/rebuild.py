import os
from pathlib import Path

from sqlalchemy.orm import Session

from .models import FileRecord


def rebuild_table_from_directory(
    db: Session,
    directory_path: str,
    clear_existing: bool = True,
) -> None:
    """Rebuild table content from files in a directory."""
    directory = Path(directory_path)

    if not directory.exists():
        raise ValueError(f"Directory does not exist: {directory_path}")
    if not directory.is_dir():
        raise ValueError(f"Not a directory: {directory_path}")

    if clear_existing:
        db.query(FileRecord).delete()
        db.commit()

    for root, _, files in os.walk(directory):
        for filename in files:
            full_path = Path(root) / filename
            record = FileRecord(
                file_path=str(full_path.resolve()),
                offset=0,
                size=full_path.stat().st_size,
                parent_id=0,
                metadata_json={},
                doc_type="",
            )
            db.add(record)

    db.commit()
