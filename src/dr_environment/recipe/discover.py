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
"""Discover recipe components from the root Taskfile."""

from __future__ import annotations

from pathlib import Path

import yaml

from dr_environment.recipe.manifests import has_any_manifest
from dr_environment.recipe.models import Component, ComponentStrategy

TASKFILE_NAMES = ("Taskfile.yml", "Taskfile.yaml")


def find_taskfile(directory: Path) -> Path | None:
    for name in TASKFILE_NAMES:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def has_environment_task(taskfile: Path) -> bool:
    data = yaml.safe_load(taskfile.read_text(encoding="utf-8")) or {}
    tasks = data.get("tasks") or {}
    return "environment" in tasks


def discover_components(recipe_path: Path) -> list[Component]:
    """Return components from root Taskfile includes."""
    root_taskfile = find_taskfile(recipe_path)
    if root_taskfile is None:
        raise FileNotFoundError(f"No Taskfile.yml found in {recipe_path}")

    data = yaml.safe_load(root_taskfile.read_text(encoding="utf-8")) or {}
    includes = data.get("includes") or {}

    components: list[Component] = []
    order = 10
    for name, spec in includes.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("internal"):
            continue

        component_dir = Path(spec.get("dir", name))
        if not component_dir.is_absolute():
            component_dir = (recipe_path / component_dir).resolve()

        taskfile = find_taskfile(component_dir)
        strategy = ComponentStrategy.DEFAULT
        if taskfile and has_environment_task(taskfile):
            strategy = ComponentStrategy.HOOK
        elif not has_any_manifest(component_dir):
            strategy = ComponentStrategy.SKIP

        components.append(
            Component(
                name=name,
                source_dir=component_dir,
                strategy=strategy,
                fragment_order=order,
            )
        )
        order += 1

    return components
