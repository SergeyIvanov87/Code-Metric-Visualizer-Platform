"""Contract for configured backend compositions."""

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING

from interfaces.access import AccessRecordEntryInterface
from interfaces.store import StorageRecordEntryInterface

if TYPE_CHECKING:
    from interfaces import RuntimeConfig


class Backend(ABC):
    """Own a configured access and storage composition."""

    access: AccessRecordEntryInterface
    store: StorageRecordEntryInterface

    @classmethod
    @abstractmethod
    def create_instance(cls, config: "RuntimeConfig") -> AbstractContextManager["Backend"]:
        """Create a configured backend and own its component lifecycles."""
