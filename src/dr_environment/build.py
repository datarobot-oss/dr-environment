"""Orchestrate docker context build."""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

import yaml

from dr_environment.cache.stages import write_component_cache_fragments
from dr_environment.discover import discover_components
from dr_environment.hooks import run_environment_hook
from dr_environment.layout import layout_components
from dr_environment.models import Component, ComponentStrategy
from dr_environment.render import (
    assemble_dockerfile,
    copy_static_template,
    render_base_fragment,
    render_kernel_fragment,
    template_root,
)
from dr_environment.validate import inspect_component, validate_all


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
    versions_file = recipe_path / ".datarobot/cli/versions.yaml"

    components = discover_components(recipe_path)
    validate_all(components)
    for component in components:
        inspect_component(component)

    if docker_context.exists():
        shutil.rmtree(docker_context)
    docker_context.mkdir(parents=True)

    versions = load_versions(versions_file)
    copy_static_template(docker_context)
    render_base_fragment(docker_context, versions)

    dockerfile_d = docker_context / "dockerfile.d"

    for component in components:
        if component.strategy == ComponentStrategy.HOOK:
            run_environment_hook(component, docker_context)
        elif component.strategy == ComponentStrategy.DEFAULT:
            inspect_component(component)
            layout_components([component], docker_context)

    active = [
        c
        for c in components
        if c.strategy == ComponentStrategy.DEFAULT and c.manifests
    ]
    final_stage = write_component_cache_fragments(active, docker_context)

    render_kernel_fragment(
        docker_context, final_stage=final_stage or "base", versions=versions
    )
    assemble_dockerfile(docker_context)

    if tarball:
        create_tarball(docker_context)

    return docker_context


def create_tarball(docker_context: Path) -> Path:
    archive = docker_context.parent / "docker_context.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(docker_context, arcname=".")
    return archive
