"""Load shared runtime settings; implementation-specific options stay opaque."""

from interfaces import RuntimeConfig
from .config import _load_yaml_mapping, load_backend_config


def load_runtime_config(backend_config=None) -> RuntimeConfig:
    backend_config = backend_config or load_backend_config()
    options = _load_yaml_mapping(backend_config.spec_path)
    return RuntimeConfig(
        options=options,
        spec_path=backend_config.spec_path,
    )
