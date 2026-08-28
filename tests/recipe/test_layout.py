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

from dr_environment.recipe.layout import (
    LOCAL_SHARED_PACKAGE,
    copy_component,
    strip_local_shared_python_package,
)
from dr_environment.recipe.models import Component, ComponentStrategy, Ecosystem, ManifestInfo


def _python_component(name: str, manifest_dir: Path, pyproject: str) -> Component:
    """Build a component whose manifests live in `manifest_dir`, which need not be its root."""
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (manifest_dir / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    return Component(
        name=name,
        source_dir=manifest_dir,
        strategy=ComponentStrategy.DEFAULT,
        manifests=[
            ManifestInfo(
                ecosystem=Ecosystem.PYTHON,
                manifest=manifest_dir / "pyproject.toml",
                lockfile=manifest_dir / "uv.lock",
            )
        ],
    )


def test_strip_local_shared_python_package_keeps_extras_in_an_inline_list() -> None:
    """The comma inside `datarobot[auth-authlib,core]` is not a dependency separator."""
    stripped = strip_local_shared_python_package(
        '[project]\ndependencies = ["core", "datarobot[auth-authlib,core]>=3.9.1"]\n'
    )

    assert stripped == '[project]\ndependencies = ["datarobot[auth-authlib,core]>=3.9.1"]\n'


def test_copy_component_strips_core_from_the_copied_pyproject(tmp_path: Path) -> None:
    """A multi-line `dependencies` list, which the inline-list regex above cannot reach."""
    pyproject = """[project]
dependencies = [
    "ag-ui-protocol>=0.1.9",
    "core",
    "datarobot[auth-authlib,core]>=3.9.1",
]

[tool.uv.sources]
core = { path = "../core", editable = true }
other = { path = "vendor", editable = true }
"""
    component = _python_component("fastapi_server", tmp_path / "fastapi_server", pyproject)

    copy_component(component, tmp_path / "ctx")

    copied = (tmp_path / "ctx/components/fastapi_server/pyproject.toml").read_text()
    assert '\n    "core",\n' not in copied
    assert "datarobot[auth-authlib,core]" in copied
    # `../core` is what a component writes; matching the path as well as the key left this
    # entry in place for every real recipe, so the source has to be keyed on the name alone.
    assert "core = { path" not in copied
    assert 'other = { path = "vendor", editable = true }' in copied


def test_copy_component_keeps_cores_own_source_entry(tmp_path: Path) -> None:
    """`core` is exempt from the rewrite, so its own source entry survives the copy."""
    component = _python_component(
        LOCAL_SHARED_PACKAGE,
        tmp_path / LOCAL_SHARED_PACKAGE,
        '[project]\nname = "core"\ndependencies = ["httpx"]\n\n[tool.uv.sources]\n'
        'core = { path = "core", editable = true }\n',
    )

    copy_component(component, tmp_path / "ctx")

    copied = (tmp_path / "ctx/components/core/pyproject.toml").read_text()
    assert 'core = { path = "core", editable = true }' in copied


def test_copy_component_from_nested_bin_manifest(tmp_path: Path) -> None:
    """The real `docs` component keeps its manifest in `docs/.bin`, not at its root."""
    component = _python_component(
        "docs", tmp_path / "docs" / ".bin", '[project]\nname = "af-component-docs"\n'
    )

    copy_component(component, tmp_path / "ctx")

    assert (tmp_path / "ctx/components/docs/pyproject.toml").is_file()
    assert (tmp_path / "ctx/components/docs/uv.lock").is_file()
