"""Load shared runtime settings; implementation-specific options stay opaque."""

from pathlib import Path

from interfaces import RuntimeConfig
from .config import _load_yaml_mapping, _required_string, load_backend_config


def load_runtime_config() -> RuntimeConfig:
    backend_config = load_backend_config()
    options = _load_yaml_mapping(backend_config.spec_path)
    return RuntimeConfig(
        storage_uri=Path(_required_string(options, "storage_uri")),
        options=options,
        spec_path=backend_config.spec_path,
    )
