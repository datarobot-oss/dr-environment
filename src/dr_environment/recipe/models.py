#
# Copyright 2026 DataRobot, Inc. and its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Shared data models for dr-environment."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Ecosystem(StrEnum):
    PYTHON = "python"
    NPM = "npm"
    GO = "go"


class LockfileStatus(StrEnum):
    OK = "ok"
    MISSING = "missing"
    STALE = "stale"
    NOT_APPLICABLE = "n/a"


class ComponentStrategy(StrEnum):
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
