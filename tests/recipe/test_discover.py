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

import yaml

from dr_environment.recipe.discover import discover_components
from dr_environment.recipe.manifests import find_manifest_file
from dr_environment.recipe.models import ComponentStrategy


def test_discover_components_finds_nested_bin_manifest(tmp_path: Path) -> None:
    recipe = tmp_path / "recipe"
    recipe.mkdir()
    docs_bin = recipe / "docs" / ".bin"
    docs_bin.mkdir(parents=True)
    (docs_bin / "pyproject.toml").write_text("[project]\nname='af-component-docs'\n")
    (docs_bin / "uv.lock").write_text("")

    taskfile = {
        "version": "3",
        "includes": {
            "docs": {"taskfile": "./docs/Taskfile.yaml", "dir": "./docs"},
        },
    }
    (recipe / "Taskfile.yml").write_text(yaml.dump(taskfile))

    components = discover_components(recipe)
    assert len(components) == 1
    assert components[0].name == "docs"
    assert components[0].strategy == ComponentStrategy.DEFAULT


def test_a_dependency_directory_is_not_mistaken_for_the_component_manifest(
    tmp_path: Path,
) -> None:
    """Any working checkout has node_modules or .venv on disk.

    Picking a dependency's manifest fails the component against a file nobody here wrote.
    """
    component = tmp_path / "docs"
    vendored = component / "node_modules" / "left-pad"
    vendored.mkdir(parents=True)
    (vendored / "package.json").write_text('{"name":"left-pad"}')

    assert find_manifest_file(component, "package.json") is None
