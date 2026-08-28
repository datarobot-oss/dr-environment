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
"""The `task environment` hook contract: PLUGIN_TESTING.md documents these five variables,
and a third-party Taskfile breaks silently if one is renamed.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from dr_environment.recipe.hooks import run_environment_hook
from dr_environment.recipe.models import Component, ComponentStrategy

CONTRACT = (
    "DOCKER_CONTEXT",
    "COMPONENT_DIR",
    "COMPONENT_NAME",
    "DOCKERFILE_FRAGMENT",
    "COMPONENT_DEST",
)


def _component(tmp_path: Path) -> Component:
    source = tmp_path / "custom"
    source.mkdir()
    (source / "Taskfile.yml").write_text(
        "version: '3'\ntasks:\n  environment:\n    cmds:\n      - true\n", encoding="utf-8"
    )
    return Component(
        name="custom",
        source_dir=source,
        strategy=ComponentStrategy.HOOK,
        fragment_order=10,
    )


def test_hook_runs_with_the_documented_contract(
    tmp_path: Path, stub_task: Callable[[str], None]
) -> None:
    # One `echo` per variable, in CONTRACT order: a renamed variable reads back empty rather
    # than shifting every value after it.
    record = tmp_path / "record"
    reads = "; ".join(f'echo "${name}"' for name in CONTRACT)
    stub_task(
        f'{{ echo "argv $*"; {reads}; }} > "{record}"; : > "$COMPONENT_DEST/copied"'
        '; printf "RUN echo hooked\\n" >> "$DOCKERFILE_FRAGMENT"'
    )
    component = _component(tmp_path)
    context = tmp_path / "ctx"
    context.mkdir()

    run_environment_hook(component, context)

    argv, *values = record.read_text().splitlines()
    fragment = context / "dockerfile.d" / "10-cache-custom.fragment"
    assert argv == f"argv -d {component.source_dir} environment"
    assert dict(zip(CONTRACT, values, strict=True)) == {
        "DOCKER_CONTEXT": str(context.resolve()),
        "COMPONENT_DIR": str(component.source_dir.resolve()),
        "COMPONENT_NAME": "custom",
        "DOCKERFILE_FRAGMENT": str(fragment.resolve()),
        "COMPONENT_DEST": str((context / "components" / "custom").resolve()),
    }
    # The stub writes into both paths, so the content proves they existed before it ran;
    # asserting they exist afterwards would pass with either mkdir below the subprocess.
    assert fragment.read_text(encoding="utf-8") == "RUN echo hooked\n"
    assert (context / "components" / "custom" / "copied").is_file()


def test_a_failing_hook_aborts_the_build(tmp_path: Path, stub_task: Callable[[str], None]) -> None:
    """Without `check=True` a failed hook yields a context whose cache was never warmed."""
    stub_task("exit 1")
    context = tmp_path / "ctx"
    context.mkdir()

    with pytest.raises(subprocess.CalledProcessError):
        run_environment_hook(_component(tmp_path), context)


def test_a_missing_task_binary_names_its_installer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """go-task is not on a stock CI runner, and a bare errno does not say what to install."""
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))

    with pytest.raises(FileNotFoundError, match="taskfile.dev"):
        run_environment_hook(_component(tmp_path), tmp_path / "ctx")
