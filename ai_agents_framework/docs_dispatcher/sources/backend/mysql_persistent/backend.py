"""MySQL access and persistent file-storage backend composition."""

from contextlib import contextmanager
from dataclasses import dataclass

from interfaces import Backend, RuntimeConfig
from interfaces.access import AccessRecordEntryInterface
from interfaces.store import StorageRecordEntryInterface
from interfaces_impl.access.mysql import MysqlAccessRecordEntry
from interfaces_impl.store.persistent import PersistentStorageRecordEntry


@dataclass(frozen=True)
class MysqlPersistentBackend(Backend):
    access: AccessRecordEntryInterface
    store: StorageRecordEntryInterface

    @classmethod
    @contextmanager
    def create_instance(cls, config: RuntimeConfig):
        with PersistentStorageRecordEntry.create_instance(config) as store:
            with MysqlAccessRecordEntry.create_instance(config) as access:
                yield cls(access=access, store=store)

