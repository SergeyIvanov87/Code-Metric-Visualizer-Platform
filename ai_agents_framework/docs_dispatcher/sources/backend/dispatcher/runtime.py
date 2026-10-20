"""Resolve the selected composition without importing its concrete classes."""

from importlib import import_module

from interfaces import Backend
from interfaces.access import AccessRecordEntryInterface
from interfaces.store.entry import StorageRecordEntryInterface
from .config import load_backend_config


def get_backend() -> Backend:
    config = load_backend_config()
    if not config.name.isidentifier():
        raise ValueError(f"Invalid dispatcher backend name: {config.name}")
    backend = import_module(config.name).backend
    if not isinstance(backend, Backend):
        raise TypeError(f"Backend {config.name} must declare interface bindings")
    if not issubclass(backend.access, AccessRecordEntryInterface):
        raise TypeError("Backend access must implement AccessRecordEntryInterface")
    if not issubclass(backend.store, StorageRecordEntryInterface):
        raise TypeError("Backend store must implement StorageRecordEntryInterface")
    return backend
