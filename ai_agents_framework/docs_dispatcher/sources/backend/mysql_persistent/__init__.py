"""MySQL and persistent-storage backend package."""

from .backend import MysqlPersistentBackend

backend = MysqlPersistentBackend

__all__ = ["MysqlPersistentBackend", "backend"]
