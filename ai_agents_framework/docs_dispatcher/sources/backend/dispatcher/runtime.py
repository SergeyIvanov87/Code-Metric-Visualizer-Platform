"""Resolve the selected composition without importing its concrete classes."""

from importlib import import_module
from contextlib import contextmanager

from interfaces import Backend, BackendContext
from interfaces.access import AccessRecordEntryInterface
from interfaces.store.entry import StorageRecordEntryInterface
from .config import load_backend_config
from .runtime_config import load_runtime_config


def _get_bindings(config) -> Backend:
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


@contextmanager
def get_backend(config=None):
    config = config or load_backend_config()
    bindings = _get_bindings(config)
    runtime = load_runtime_config(config)
    store = bindings.store.from_config(runtime)
    with bindings.access.open(runtime) as access:
        yield BackendContext(access=access, store=store)
