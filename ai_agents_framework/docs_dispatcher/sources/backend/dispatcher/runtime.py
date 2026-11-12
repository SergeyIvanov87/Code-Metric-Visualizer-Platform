"""Resolve the selected backend implementation without owning its components."""

from importlib import import_module

from interfaces import Backend
from .runtime_config import load_runtime_config


def _get_backend_class(config) -> type[Backend]:
    if not config.name.isidentifier():
        raise ValueError(f"Invalid dispatcher backend name: {config.name}")
    backend_class = import_module(config.name).backend
    if not isinstance(backend_class, type) or not issubclass(backend_class, Backend):
        raise TypeError(f"Backend {config.name} must implement Backend")
    return backend_class


def get_backend(config):
    runtime = load_runtime_config(config)
    return _get_backend_class(config).create_instance(runtime)
