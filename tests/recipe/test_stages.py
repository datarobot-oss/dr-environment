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

from dr_environment.recipe.cache.stages import PREVIOUS_STAGE, write_component_cache_fragment
from dr_environment.recipe.layout import LOCAL_SHARED_PACKAGE
from dr_environment.recipe.models import Component, ComponentStrategy, Ecosystem, ManifestInfo


def test_cache_stages_chain_from_kernel() -> None:
    assert PREVIOUS_STAGE == "kernel"


def test_python_cache_fragment_uses_uv_sync(tmp_path: Path) -> None:
    component = Component(
        name="agent",
        source_dir=tmp_path,
        strategy=ComponentStrategy.DEFAULT,
        fragment_order=10,
        manifests=[
            ManifestInfo(
                ecosystem=Ecosystem.PYTHON,
                manifest=tmp_path / "pyproject.toml",
                lockfile=tmp_path / "uv.lock",
            )
        ],
    )
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
    component = Component(
        name=LOCAL_SHARED_PACKAGE,
        source_dir=tmp_path,
        strategy=ComponentStrategy.DEFAULT,
        fragment_order=11,
        manifests=[
            ManifestInfo(
                ecosystem=Ecosystem.PYTHON,
                manifest=tmp_path / "pyproject.toml",
                lockfile=tmp_path / "uv.lock",
            )
        ],
    )
    docker_context = tmp_path / "ctx"
    write_component_cache_fragment(component, docker_context, previous_stage="cache-agent")

    content = (docker_context / "dockerfile.d" / "11-cache-core.fragment").read_text()
    assert "--all-extras" in content
    assert "--all-groups" in content
    assert f"--no-install-package {LOCAL_SHARED_PACKAGE}" not in content
