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

from dr_environment.recipe.cache.stages import write_component_cache_fragment
from dr_environment.recipe.layout import LOCAL_SHARED_PACKAGE
from dr_environment.recipe.models import Component, ComponentStrategy, Ecosystem, ManifestInfo

MANIFEST_NAMES = {
    Ecosystem.PYTHON: "pyproject.toml",
    Ecosystem.NPM: "package.json",
    Ecosystem.GO: "go.mod",
}


def _component(tmp_path: Path, name: str, ecosystem: Ecosystem, order: int) -> Component:
    return Component(
        name=name,
        source_dir=tmp_path,
        strategy=ComponentStrategy.DEFAULT,
        fragment_order=order,
        manifests=[
            ManifestInfo(
                ecosystem=ecosystem,
                manifest=tmp_path / MANIFEST_NAMES[ecosystem],
                lockfile=tmp_path / "lock",
            )
        ],
    )


def test_python_cache_fragment_uses_uv_sync(tmp_path: Path) -> None:
    component = _component(tmp_path, "agent", Ecosystem.PYTHON, 10)
    docker_context = tmp_path / "ctx"

    write_component_cache_fragment(component, docker_context, previous_stage="kernel")

    content = (docker_context / "dockerfile.d" / "10-cache-agent.fragment").read_text()
    assert content.startswith("FROM kernel AS cache-agent")
    assert "COPY --chown=notebooks:notebooks components/agent/" in content
    assert "uv sync" in content
    assert "--all-extras" in content
    assert "--all-groups" in content
    assert "--python-platform" not in content
    assert "USER root" not in content
    assert "chown -R notebooks" not in content
    assert f"--no-install-package {LOCAL_SHARED_PACKAGE}" in content
    # Wheelhouse population: export the deploy-time set and download the exact published
    # artifacts into the shared find-links directory.
    assert "uv export --frozen --no-dev --no-emit-local --no-emit-project" in content
    assert "pip download --no-deps --no-cache-dir" in content
    assert "--dest /opt/wheelhouse" in content
    assert "rm -rf /tmp/uv-cache-warm-agent" in content


def test_python_cache_fragment_core_skips_no_install_package(tmp_path: Path) -> None:
    component = _component(tmp_path, LOCAL_SHARED_PACKAGE, Ecosystem.PYTHON, 11)
    docker_context = tmp_path / "ctx"

    write_component_cache_fragment(component, docker_context, previous_stage="cache-agent")

    content = (docker_context / "dockerfile.d" / "11-cache-core.fragment").read_text()
    assert f"--no-install-package {LOCAL_SHARED_PACKAGE}" not in content


def test_go_cache_fragment_downloads_modules_into_the_shared_cache(tmp_path: Path) -> None:
    component = _component(tmp_path, "gateway", Ecosystem.GO, 12)
    docker_context = tmp_path / "ctx"

    write_component_cache_fragment(component, docker_context, previous_stage="cache-agent")

    content = (docker_context / "dockerfile.d" / "12-cache-gateway.fragment").read_text()
    assert content.startswith("FROM cache-agent AS cache-gateway")
    assert "ENV GOMODCACHE=/opt/cache/go/pkg/mod GOCACHE=/opt/cache/go/build" in content
    # `all`, not the default: the offline image has to serve test and tool imports too.
    assert "RUN go mod download all" in content


def test_npm_cache_fragment_installs_dev_dependencies_into_the_shared_cache(
    tmp_path: Path,
) -> None:
    component = _component(tmp_path, "frontend", Ecosystem.NPM, 12)
    docker_context = tmp_path / "ctx"

    write_component_cache_fragment(component, docker_context, previous_stage="cache-agent")

    content = (docker_context / "dockerfile.d" / "12-cache-frontend.fragment").read_text()
    assert content.startswith("FROM cache-agent AS cache-frontend")
    assert "ENV NPM_CONFIG_CACHE=/opt/cache/npm" in content
    # `--include=dev` is what puts the build tooling in the cache; without it an offline
    # frontend build has no devDependencies to install from.
    assert "RUN npm ci --include=dev --cache /opt/cache/npm" in content
