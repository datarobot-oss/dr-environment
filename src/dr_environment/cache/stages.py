"""Dockerfile cache stage fragment generators."""

from __future__ import annotations

from pathlib import Path

from dr_environment.layout import LOCAL_SHARED_PACKAGE
from dr_environment.models import Component, Ecosystem

PREVIOUS_STAGE = "base"
RUNTIME_USER = "notebooks"
UV_CACHE = "/opt/cache/uv"
NPM_CACHE = "/opt/cache/npm"
GO_MOD_CACHE = "/opt/cache/go/pkg/mod"
GO_BUILD_CACHE = "/opt/cache/go/build"
PYTHON_PLATFORM = "x86_64-manylinux_2_28"


def write_component_cache_fragment(
    component: Component,
    docker_context: Path,
    *,
    previous_stage: str,
) -> str:
    """Write cache fragment for component; return new stage name."""
    stage_name = f"cache-{component.name}"
    lines: list[str] = [f"FROM {previous_stage} AS {stage_name}"]

    for info in component.manifests:
        if info.ecosystem == Ecosystem.PYTHON:
            lines.extend(_python_cache_lines(component.name))
        elif info.ecosystem == Ecosystem.NPM:
            lines.extend(_npm_cache_lines(component.name))
        elif info.ecosystem == Ecosystem.GO:
            lines.extend(_go_cache_lines(component.name))

    fragment_path = (
        docker_context
        / "dockerfile.d"
        / f"{component.fragment_order:02d}-cache-{component.name}.fragment"
    )
    fragment_path.parent.mkdir(parents=True, exist_ok=True)
    fragment_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stage_name


def write_component_cache_fragments(
    components: list[Component],
    docker_context: Path,
) -> str:
    """Write all default component cache fragments; return final stage name."""
    previous = PREVIOUS_STAGE
    for component in components:
        if not component.manifests:
            continue
        previous = write_component_cache_fragment(
            component, docker_context, previous_stage=previous
        )
    return previous


def _copy_component_tree(component_name: str) -> str:
    return (
        f"COPY --chown={RUNTIME_USER}:{RUNTIME_USER} "
        f"components/{component_name}/ /tmp/cache-work/{component_name}/"
    )


def _python_cache_lines(component_name: str) -> list[str]:
    sync_flags = "--frozen --no-install-project"
    if component_name != LOCAL_SHARED_PACKAGE:
        sync_flags += f" --no-install-package {LOCAL_SHARED_PACKAGE}"

    warm_venv = f"/tmp/uv-cache-warm-{component_name}"
    return [
        f"ENV UV_CACHE_DIR={UV_CACHE}",
        _copy_component_tree(component_name),
        f"WORKDIR /tmp/cache-work/{component_name}",
        f"RUN UV_PROJECT_ENVIRONMENT={warm_venv} \\",
        f"    uv sync {sync_flags} --python-platform {PYTHON_PLATFORM} \\",
        "        --python ${VENV_PATH}/bin/python \\",
        f"    && rm -rf {warm_venv}",
    ]


def _npm_cache_lines(component_name: str) -> list[str]:
    return [
        f"ENV NPM_CONFIG_CACHE={NPM_CACHE}",
        _copy_component_tree(component_name),
        f"WORKDIR /tmp/cache-work/{component_name}",
        f"RUN npm ci --include=dev --cache {NPM_CACHE}",
    ]


def _go_cache_lines(component_name: str) -> list[str]:
    return [
        f"ENV GOMODCACHE={GO_MOD_CACHE} GOCACHE={GO_BUILD_CACHE}",
        _copy_component_tree(component_name),
        f"WORKDIR /tmp/cache-work/{component_name}",
        "RUN go mod download all",
    ]
