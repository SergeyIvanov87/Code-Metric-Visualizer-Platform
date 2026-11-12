"""Shared dispatcher contracts and runtime configuration."""

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .backend import Backend
from .schema import RecordSchema


@dataclass(frozen=True)
class RuntimeConfig:
    options: Mapping[str, str]
    spec_path: Path
