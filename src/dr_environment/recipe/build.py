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
"""Orchestrate docker context build."""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

import yaml

from dr_environment.recipe.cache.stages import write_component_cache_fragments
from dr_environment.recipe.discover import discover_components
from dr_environment.recipe.hooks import run_environment_hook
from dr_environment.recipe.layout import copy_component
from dr_environment.recipe.models import ComponentStrategy
from dr_environment.recipe.render import (
    assemble_dockerfile,
    copy_fragment_assets,
    render_base_fragment,
    render_build_deps_fragment,
    render_kernel_setup_fragment,
    render_offline_fragment,
    render_user_fragment,
    render_versions_fragment,
)
from dr_environment.recipe.validate import validate_all


def load_versions(versions_file: Path) -> dict:
    if not versions_file.is_file():
        return {}
    return yaml.safe_load(versions_file.read_text(encoding="utf-8")) or {}


def build(
    recipe_path: Path,
    target: Path,
    *,
    tarball: bool = True,
) -> Path:
    recipe_path = recipe_path.resolve()
    docker_context = target.resolve() if target.is_absolute() else (Path.cwd() / target).resolve()
    # The target is emptied before it is written, so it may only be a directory this tool
    # generated, or an empty one. `--target .` (also an unset shell variable, since `Path("")`
    # is `Path(".")`) and `--target <component>` both reach here and deleted recipe source.
    if (
        docker_context.is_dir()
        and any(docker_context.iterdir())
        and not (docker_context / "dockerfile.d").is_dir()
    ):
        raise ValueError(
            f"refusing to build into {docker_context}: it is not empty and was not generated "
            "by this tool"
        )
    versions_file = recipe_path / ".datarobot/cli/versions.yaml"

    components = discover_components(recipe_path)
    validate_all(components)

    if docker_context.exists():
        shutil.rmtree(docker_context)
    docker_context.mkdir(parents=True)

    versions = load_versions(versions_file)
    copy_fragment_assets(docker_context)
    render_base_fragment(docker_context)
    render_user_fragment(docker_context)
    render_versions_fragment(docker_context, versions)
    render_build_deps_fragment(docker_context)
    render_kernel_setup_fragment(docker_context)

    for component in components:
        if component.strategy == ComponentStrategy.HOOK:
            run_environment_hook(component, docker_context)
        elif component.strategy == ComponentStrategy.DEFAULT:
            copy_component(component, docker_context)

    active = [c for c in components if c.strategy == ComponentStrategy.DEFAULT and c.manifests]
    cache_stage = write_component_cache_fragments(active, docker_context)

    render_offline_fragment(docker_context, cache_stage=cache_stage)
    assemble_dockerfile(docker_context)

    if tarball:
        create_tarball(docker_context)

    return docker_context


def create_tarball(docker_context: Path) -> Path:
    archive = docker_context.parent / "docker_context.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(docker_context, arcname=".")
    return archive
