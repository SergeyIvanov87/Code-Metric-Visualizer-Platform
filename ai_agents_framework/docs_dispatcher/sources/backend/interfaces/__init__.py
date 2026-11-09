"""A backend binds independent access and storage implementations."""

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .access import AccessRecordEntryInterface
from .store.entry import StorageRecordEntryInterface


@dataclass(frozen=True)
class Backend:
    access: type[AccessRecordEntryInterface]
    store: type[StorageRecordEntryInterface]


@dataclass(frozen=True)
class RuntimeConfig:
    options: Mapping[str, str]
    spec_path: Path


@dataclass(frozen=True)
class BackendContext:
    access: AccessRecordEntryInterface
    store: StorageRecordEntryInterface
