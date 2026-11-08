"""Public configuration import for dispatcher entrypoint scripts."""

from backend.dispatcher.config import BackendDispatcher, load_backend_config

__all__ = ["BackendDispatcher", "load_backend_config"]
