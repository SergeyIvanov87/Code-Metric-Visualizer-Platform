from pathlib import Path


def read_metadata_text(value: str | None) -> str:
    if not value:
        return ""
    path = Path(value)
    return path.read_text() if path.exists() else value
