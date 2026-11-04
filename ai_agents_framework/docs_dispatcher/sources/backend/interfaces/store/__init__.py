"""Storage schema, interface, and common record model."""

from .entry import StorageRecordEntryInterface, StorageRecordSchema
from .models import StorageRecord

__all__ = ["StorageRecordEntryInterface", "StorageRecordSchema", "StorageRecord"]
