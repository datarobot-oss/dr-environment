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

import re
from collections.abc import Sequence
from dataclasses import dataclass
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

# Every cache dir the offline runtime image can copy out of a cache stage.
CACHE_COPY_PATHS = (
    UV_CACHE,
    NPM_CACHE,
    GO_CACHE_ROOT,
    WHEELHOUSE,
)

#: The cache dirs each ecosystem's stage writes, so the offline stage copies only those.
_ECOSYSTEM_PATHS = {
    Ecosystem.PYTHON: (UV_CACHE, WHEELHOUSE),
    Ecosystem.NPM: (NPM_CACHE,),
    Ecosystem.GO: (GO_CACHE_ROOT,),
}

# The deployed model runs as uid 1000, not `notebooks`, and opens uv cache files for
# writing at startup, so they must be writable by any uid. Each stage makes the files it
# wrote world-writable itself: a chmod over the merged cache would copy all of it into a
# new layer, and `COPY --chmod` needs BuildKit.
_UV_CACHE_CHMOD = f"chmod -R a+rwX {UV_CACHE}"

_STAGE_DEF = re.compile(r"^FROM\s+(?:--\S+\s+)*\S+\s+AS\s+(\S+)\s*$", re.MULTILINE | re.I)


@dataclass(frozen=True)
class CacheStage:
    """A cache stage and the cache dirs the offline stage copies out of it."""

    name: str
    paths: tuple[str, ...]


def stage_name(component_name: str) -> str:
    return f"cache-{component_name}"


def _ordered(paths: set[str]) -> tuple[str, ...]:
    return tuple(path for path in CACHE_COPY_PATHS if path in paths)


def write_component_cache_fragment(component: Component, docker_context: Path) -> CacheStage:
    """Write the cache fragment for *component*; return its stage.

    Every cache stage builds `FROM kernel` rather than from the previous one, so BuildKit
    warms the components in parallel and a change to one component's lockfile rebuilds
    only that component's stage. The offline stage merges them by copying each stage's
    cache dirs in turn.
    """
    name = stage_name(component.name)
    lines: list[str] = [f"FROM {PREVIOUS_STAGE} AS {name}"]
    paths: set[str] = set()

    for info in component.manifests:
        paths.update(_ECOSYSTEM_PATHS[info.ecosystem])
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
    return CacheStage(name, _ordered(paths))


def write_component_cache_fragments(
    components: Sequence[Component],
    docker_context: Path,
) -> list[CacheStage]:
    """Write all default component cache fragments; return their stages in order."""
    return [
        write_component_cache_fragment(component, docker_context)
        for component in components
        if component.manifests
    ]


def hook_fragment_header(component_name: str) -> str:
    """Return the first line of a hook's fragment, giving its instructions their own stage."""
    return f"FROM {PREVIOUS_STAGE} AS {stage_name(component_name)}\n"


def finish_hook_fragment(fragment_path: Path, component_name: str) -> CacheStage:
    """Close the fragment a hook wrote; return the stage to copy its caches out of.

    That is the last stage the fragment defines: the one it was given, unless the hook
    opened its own. A hook may write any cache, so all cache dirs are copied, and its uv
    files are made world-writable here because the hook's instructions do not do it.
    """
    content = fragment_path.read_text(encoding="utf-8")
    stages = _STAGE_DEF.findall(content)
    name = stages[-1] if stages else stage_name(component_name)
    if not content.endswith("\n"):
        content += "\n"
    # As root: a hook may leave root-owned files in the cache.
    content += f"USER root\nRUN {_UV_CACHE_CHMOD}\n"
    fragment_path.write_text(content, encoding="utf-8")
    return CacheStage(name, CACHE_COPY_PATHS)


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
        # No --only-binary=:all: here (unlike the copier/build-deps wheelhouse downloads):
        # components pull in arbitrary packages we don't control, and plenty of legitimate
        # pure-Python packages have stopped publishing wheels without being any less safe to
        # build offline (e.g. rouge-score >=0.0.7 is sdist-only but pure Python, needing only
        # the setuptools we already bake in) — rejecting all sdists here would fail builds
        # over packages that build fine, not just the genuinely risky ones.
        # pip installs with --no-config: `uv pip` honours the component's `[tool.uv]`, and a
        # component that excludes pip there would make the install a silent no-op.
        f"RUN UV_PROJECT_ENVIRONMENT={warm_venv} \\",
        f"    uv sync {sync_flags} \\",
        '        --python "${VENV_PATH}/bin/python" \\',
        f"    && uv pip install --no-config --no-cache --python {warm_venv}/bin/python pip \\",
        "    && uv export --frozen --no-dev --no-emit-local --no-emit-project \\",
        f"        -o {wheelhouse_req} \\",
        f"    && {warm_venv}/bin/python -m pip download --no-deps --no-cache-dir \\",
        f"        -r {wheelhouse_req} --dest {WHEELHOUSE} \\",
        f"    && rm -rf {warm_venv} {wheelhouse_req} \\",
        # Same RUN, so only the files this stage wrote are touched (see _UV_CACHE_CHMOD).
        f"    && {_UV_CACHE_CHMOD}",
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
