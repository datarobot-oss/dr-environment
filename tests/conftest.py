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
"""Shared fixtures for the test suite."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

FIXTURE_RECIPE = Path(__file__).resolve().parent / "fixtures" / "recipe"


@pytest.fixture(scope="session")
def _locked_recipe(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Lock the fixture recipe once per session; tests copy from the result.

    Generated rather than committed: `validate_all` runs each ecosystem's own check, which a
    committed lockfile fails as soon as that tool changes its format.
    """
    for tool in ("uv", "npm"):
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} is required to lock and validate the fixture recipe")

    root = tmp_path_factory.mktemp("locked-recipe") / "recipe"
    shutil.copytree(FIXTURE_RECIPE, root)
    for component, command in (
        ("agent", ["uv", "lock"]),
        ("frontend", ["npm", "install", "--package-lock-only", "--ignore-scripts"]),
    ):
        locked = subprocess.run(
            command, cwd=root / component, capture_output=True, text=True, check=False
        )
        if locked.returncode != 0:
            pytest.fail(f"could not lock fixture component {component}:\n{locked.stderr}")
    return root


@pytest.fixture
def recipe(_locked_recipe: Path, tmp_path: Path) -> Path:
    """Copy the locked fixture recipe, so a test is free to mutate its own tree."""
    root = tmp_path / "recipe"
    shutil.copytree(_locked_recipe, root)
    return root


@pytest.fixture
def stub_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    """Put a `task` on PATH running the given shell body, so go-task is not needed."""

    def install(body: str) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        stub = bin_dir / "task"
        stub.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        stub.chmod(0o755)
        # Prepended, not replaced: the stub has to win over a real go-task, while the body
        # still needs the shell utilities on the inherited PATH.
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    return install
