"""Default composition: MySQL record access and persistent file storage."""

from interfaces import Backend
from .access.mysql import MysqlAccessRecordEntry
from .store.persistent import PersistentStorageRecordEntry

backend = Backend(access=MysqlAccessRecordEntry, store=PersistentStorageRecordEntry)
