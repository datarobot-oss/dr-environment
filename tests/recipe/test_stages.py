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
from pathlib import Path

from dr_environment.recipe.cache.stages import (
    CacheStage,
    finish_hook_fragment,
    hook_fragment_header,
    write_component_cache_fragment,
    write_component_cache_fragments,
)
from dr_environment.recipe.layout import LOCAL_SHARED_PACKAGE
from dr_environment.recipe.models import Component, ComponentStrategy, Ecosystem, ManifestInfo


def _component(tmp_path: Path, name: str, ecosystem: Ecosystem, order: int) -> Component:
    """Build a component; the fragment comes from the ecosystem alone, so paths go unread."""
    return Component(
        name=name,
        source_dir=tmp_path,
        strategy=ComponentStrategy.DEFAULT,
        fragment_order=order,
        manifests=[
            ManifestInfo(ecosystem=ecosystem, manifest=tmp_path / "manifest", lockfile=None)
        ],
    )


def test_python_cache_fragment_uses_uv_sync(tmp_path: Path) -> None:
    component = _component(tmp_path, "agent", Ecosystem.PYTHON, 10)
    docker_context = tmp_path / "ctx"

    stage = write_component_cache_fragment(component, docker_context)

    assert stage == CacheStage("cache-agent", ("/opt/cache/uv", "/opt/wheelhouse"))
    content = (docker_context / "dockerfile.d" / "10-cache-agent.fragment").read_text()
    assert content.startswith("FROM kernel AS cache-agent")
    # This is the dir the offline stage copies out of. Warming any other one ships an empty cache.
    assert "ENV UV_CACHE_DIR=/opt/cache/uv" in content
    assert "COPY --chown=notebooks:notebooks components/agent/" in content
    assert "uv sync" in content
    assert "--all-extras" in content
    assert "--all-groups" in content
    # Every stage descends from `FROM --platform=${TARGETPLATFORM}`, so resolving for another
    # platform would put wheels in the cache the image cannot run.
    assert "--python-platform" not in content
    # Ownership comes from the `COPY --chown` above; a `chown -R` would copy the cache into a
    # new layer, and `USER root` is not needed since the stage owns what it writes.
    assert "USER root" not in content
    assert "chown -R notebooks" not in content
    # The deployed model (uid 1000) writes to the uv cache, so the stage makes the files it
    # wrote world-writable in the same RUN as the sync: a later RUN would copy them all into
    # a second layer, which is what the old cache-perms stage cost.
    run = content.split("RUN UV_PROJECT_ENVIRONMENT=", 1)[1]
    assert run.rstrip().endswith("&& chmod -R a+rwX /opt/cache/uv")
    assert "\nRUN " not in run, "the chmod must be in the same RUN as the sync"
    assert f"--no-install-package {LOCAL_SHARED_PACKAGE}" in content
    # Wheelhouse population: export the deploy-time set and download the exact published
    # artifacts into the shared find-links directory.
    assert "uv export --frozen --no-dev --no-emit-local --no-emit-project" in content
    # A component that excludes pip in its `[tool.uv]` would turn this install into a no-op.
    assert "uv pip install --no-config --no-cache" in content
    assert "pip download --no-deps --no-cache-dir" in content
    assert "--dest /opt/wheelhouse" in content
    assert "rm -rf /tmp/uv-cache-warm-agent" in content


def test_python_cache_fragment_core_skips_no_install_package(tmp_path: Path) -> None:
    component = _component(tmp_path, LOCAL_SHARED_PACKAGE, Ecosystem.PYTHON, 11)
    docker_context = tmp_path / "ctx"

    write_component_cache_fragment(component, docker_context)

    content = (docker_context / "dockerfile.d" / "11-cache-core.fragment").read_text()
    assert f"--no-install-package {LOCAL_SHARED_PACKAGE}" not in content


def test_go_cache_fragment_downloads_modules_into_the_shared_cache(tmp_path: Path) -> None:
    component = _component(tmp_path, "gateway", Ecosystem.GO, 12)
    docker_context = tmp_path / "ctx"

    stage = write_component_cache_fragment(component, docker_context)

    # UV_CACHE is omitted on purpose: this stage does not fill it. The offline stage
    # inherits the kernel tools cache and chmods it when no stage copies UV_CACHE.
    assert stage == CacheStage("cache-gateway", ("/opt/cache/go",))
    content = (docker_context / "dockerfile.d" / "12-cache-gateway.fragment").read_text()
    assert content.startswith("FROM kernel AS cache-gateway")
    assert "ENV GOMODCACHE=/opt/cache/go/pkg/mod GOCACHE=/opt/cache/go/build" in content
    # `all` rather than the default, so the offline image can serve test and tool imports too.
    assert "RUN go mod download all" in content
    assert "chmod" not in content


def test_npm_cache_fragment_installs_dev_dependencies_into_the_shared_cache(
    tmp_path: Path,
) -> None:
    component = _component(tmp_path, "frontend", Ecosystem.NPM, 12)
    docker_context = tmp_path / "ctx"

    stage = write_component_cache_fragment(component, docker_context)

    # UV_CACHE is omitted on purpose: this stage does not fill it. The offline stage
    # inherits the kernel tools cache and chmods it when no stage copies UV_CACHE.
    assert stage == CacheStage("cache-frontend", ("/opt/cache/npm",))
    content = (docker_context / "dockerfile.d" / "12-cache-frontend.fragment").read_text()
    assert content.startswith("FROM kernel AS cache-frontend")
    assert "ENV NPM_CONFIG_CACHE=/opt/cache/npm" in content
    # `--include=dev` is what puts the build tooling in the cache. Without it an offline
    # frontend build has no devDependencies to install from.
    assert "RUN npm ci --include=dev --cache /opt/cache/npm" in content
    assert "chmod" not in content


def test_every_cache_stage_builds_from_kernel_so_they_run_in_parallel(tmp_path: Path) -> None:
    """Chaining the stages serialises the cache warm and makes a lockfile change in one
    component rebuild every stage after it.
    """
    components = [
        _component(tmp_path, "agent", Ecosystem.PYTHON, 10),
        _component(tmp_path, "frontend", Ecosystem.NPM, 11),
        _component(tmp_path, "gateway", Ecosystem.GO, 12),
    ]
    docker_context = tmp_path / "ctx"

    stages = write_component_cache_fragments(components, docker_context)

    assert [stage.name for stage in stages] == ["cache-agent", "cache-frontend", "cache-gateway"]
    for fragment in sorted((docker_context / "dockerfile.d").glob("*.fragment")):
        assert fragment.read_text().startswith("FROM kernel AS cache-")


def test_finish_hook_fragment_copies_from_the_stage_the_hook_ended_in(tmp_path: Path) -> None:
    fragment = tmp_path / "20-cache-custom.fragment"

    fragment.write_text(hook_fragment_header("custom") + "RUN echo hooked")
    assert finish_hook_fragment(fragment, "custom").name == "cache-custom"
    # Unknown writes, so the uv files are made world-writable after them, as root in case a
    # hook left root-owned files.
    assert fragment.read_text().endswith(
        "RUN echo hooked\nUSER root\nRUN chmod -R a+rwX /opt/cache/uv\n"
    )

    fragment.write_text(hook_fragment_header("custom") + "FROM kernel AS warm\nRUN true\n")
    stage = finish_hook_fragment(fragment, "custom")
    assert stage.name == "warm", "a stage the hook opened itself is where its caches are"
    assert set(stage.paths) == {
        "/opt/cache/uv",
        "/opt/cache/npm",
        "/opt/cache/go",
        "/opt/wheelhouse",
    }
