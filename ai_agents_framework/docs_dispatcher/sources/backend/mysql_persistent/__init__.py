"""Default composition: MySQL record access and persistent file storage."""

from interfaces import Backend
from interfaces_impl.access.mysql import MysqlAccessRecordEntry
from interfaces_impl.store.persistent import PersistentStorageRecordEntry

backend = Backend(access=MysqlAccessRecordEntry, store=PersistentStorageRecordEntry)
