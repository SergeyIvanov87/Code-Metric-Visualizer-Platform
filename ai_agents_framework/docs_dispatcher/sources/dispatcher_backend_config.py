"""Public configuration import for dispatcher entrypoint scripts."""

from backend.dispatcher.config import BackendConfig, load_backend_config

__all__ = ["BackendConfig", "load_backend_config"]
