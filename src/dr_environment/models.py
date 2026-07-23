"""Shared data models for dr-environment."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Ecosystem(str, Enum):
    PYTHON = "python"
    NPM = "npm"
    GO = "go"


class LockfileStatus(str, Enum):
    OK = "ok"
    MISSING = "missing"
    STALE = "stale"
    NOT_APPLICABLE = "n/a"


class ComponentStrategy(str, Enum):
    DEFAULT = "default"
    HOOK = "hook"
    SKIP = "skip"


@dataclass
class ManifestInfo:
    ecosystem: Ecosystem
    manifest: Path
    lockfile: Path | None
    status: LockfileStatus = LockfileStatus.NOT_APPLICABLE
    message: str = ""


@dataclass
class Component:
    name: str
    source_dir: Path
    strategy: ComponentStrategy = ComponentStrategy.DEFAULT
    manifests: list[ManifestInfo] = field(default_factory=list)
    fragment_order: int = 0

    @property
    def dest_name(self) -> str:
        return self.name
