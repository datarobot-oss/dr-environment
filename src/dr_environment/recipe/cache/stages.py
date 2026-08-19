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
"""Dockerfile cache stage fragment generators."""

from __future__ import annotations

from pathlib import Path

from dr_environment.recipe.layout import LOCAL_SHARED_PACKAGE
from dr_environment.recipe.models import Component, Ecosystem

PREVIOUS_STAGE = "kernel"
RUNTIME_USER = "notebooks"
UV_CACHE = "/opt/cache/uv"
NPM_CACHE = "/opt/cache/npm"
GO_MOD_CACHE = "/opt/cache/go/pkg/mod"
GO_BUILD_CACHE = "/opt/cache/go/build"
GO_CACHE_ROOT = "/opt/cache/go"
# Flat find-links directory of the exact published Python wheels/sdists. Kept separate from
# the uv cache: DataRobot builds the FastAPI custom application FROM this image with
# `uv pip install --system --no-cache`, and `--no-cache` makes uv ignore UV_CACHE. uv still
# honours find-links, so the offline stage points UV_FIND_LINKS here (see _python_cache_lines).
WHEELHOUSE = "/opt/wheelhouse"

# Paths copied from the final cache stage into the offline runtime image.
CACHE_COPY_PATHS = (
    UV_CACHE,
    NPM_CACHE,
    GO_CACHE_ROOT,
    WHEELHOUSE,
)


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
) -> str | None:
    """Write all default component cache fragments; return final cache stage name."""
    previous = PREVIOUS_STAGE
    wrote = False
    for component in components:
        if not component.manifests:
            continue
        wrote = True
        previous = write_component_cache_fragment(
            component, docker_context, previous_stage=previous
        )
    return previous if wrote else None


def _copy_component_tree(component_name: str) -> str:
    return (
        f"COPY --chown={RUNTIME_USER}:{RUNTIME_USER} "
        f"components/{component_name}/ /tmp/cache-work/{component_name}/"
    )


def _python_cache_lines(component_name: str) -> list[str]:
    sync_flags = "--frozen --no-install-project --all-extras --all-groups"
    if component_name != LOCAL_SHARED_PACKAGE:
        sync_flags += f" --no-install-package {LOCAL_SHARED_PACKAGE}"

    warm_venv = f"/tmp/uv-cache-warm-{component_name}"
    wheelhouse_req = f"/tmp/wheelhouse-req-{component_name}.txt"
    return [
        f"ENV UV_CACHE_DIR={UV_CACHE}",
        _copy_component_tree(component_name),
        f"WORKDIR /tmp/cache-work/{component_name}",
        # Warm the uv cache; agent/MCP custom models install from it at runtime with
        # `uv sync` (see the start_server.sh block in the offline stage). Mirror the same
        # dependencies into the shared wheelhouse in the same RUN (see WHEELHOUSE above for
        # why DataRobot's `--no-cache` app build cannot read the uv cache): `pip download`
        # fetches the exact published artifacts, so their hashes match the ones `uv export`
        # writes into the requirements file at deploy time; rebuilt wheels would not. Export
        # exactly what DataRobot installs: production dependencies, project and workspace
        # members excluded. warm_venv must be removed in this same RUN — splitting the sync
        # and the rm across RUNs would bake the multi-GB venv into the earlier layer for good.
        f"RUN UV_PROJECT_ENVIRONMENT={warm_venv} \\",
        f"    uv sync {sync_flags} \\",
        "        --python ${VENV_PATH}/bin/python \\",
        f"    && uv pip install --no-cache --python {warm_venv}/bin/python pip \\",
        "    && uv export --frozen --no-dev --no-emit-local --no-emit-project \\",
        f"        -o {wheelhouse_req} \\",
        f"    && {warm_venv}/bin/python -m pip download --no-deps --no-cache-dir \\",
        f"        -r {wheelhouse_req} --dest {WHEELHOUSE} \\",
        f"    && rm -rf {warm_venv} {wheelhouse_req}",
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
