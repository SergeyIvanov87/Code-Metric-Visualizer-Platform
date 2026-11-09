"""Select and open a backend without exposing configuration to API scripts."""

import sys
from pathlib import Path

# Backend plugins use their own package root in both API and tester processes.
_BACKENDS_ROOT = str(Path(__file__).resolve().parents[1])
if _BACKENDS_ROOT not in sys.path:
    sys.path.insert(0, _BACKENDS_ROOT)

from .config import load_backend_config
from .runtime import get_backend


class BackendDispatcher:
    def __init__(self):
        self._config = load_backend_config()

    def get_backend(self):
        return get_backend(self._config)
