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


def discover_components(
    recipe_path: Path,
    *,
    component_filter: set[str] | None = None,
    skip_hooks: bool = False,
) -> list[Component]:
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
        if component_filter and name not in component_filter:
            continue

        component_dir = Path(spec.get("dir", name))
        if not component_dir.is_absolute():
            component_dir = (recipe_path / component_dir).resolve()

        taskfile = find_taskfile(component_dir)
        strategy = ComponentStrategy.DEFAULT
        if not skip_hooks and taskfile and has_environment_task(taskfile):
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
