"""Backend-neutral document and chunk record schema."""

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any


@dataclass
class RecordSchema:
    """Logical record shared by access and storage implementations."""

    file_uri: str | Path
    id: int | None = None
    offset: int = -1
    size: int = -1
    parent_id: int = 0
    metadata: dict[str, Any] | None = field(default_factory=dict)
    doc_type: str = ""

    def get_difference(
        self,
        other: "RecordSchema",
    ) -> dict[str, tuple[Any, Any]]:
        """Return fields whose values differ as ``(self, other)`` pairs."""
        if not isinstance(other, RecordSchema):
            raise TypeError("other must be a RecordSchema")

        return {
            schema_field.name: (
                getattr(self, schema_field.name),
                getattr(other, schema_field.name),
            )
            for schema_field in fields(self)
            if getattr(self, schema_field.name)
            != getattr(other, schema_field.name)
        }

    @property
    def file_path(self) -> str | Path:
        """Compatibility name used by database-facing code."""
        return self.file_uri

    @file_path.setter
    def file_path(self, value: str | Path) -> None:
        self.file_uri = value

    @property
    def unique_id(self) -> int | None:
        """Compatibility name used by storage-facing code."""
        return self.id

    @unique_id.setter
    def unique_id(self, value: int | None) -> None:
        self.id = value

    @property
    def metadata_json(self) -> dict[str, Any] | None:
        """Compatibility name used by database-facing code."""
        return self.metadata

    @metadata_json.setter
    def metadata_json(self, value: dict[str, Any] | None) -> None:
        self.metadata = value
