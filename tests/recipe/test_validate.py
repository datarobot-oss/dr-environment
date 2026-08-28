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
from unittest.mock import patch

import pytest

from dr_environment.recipe.models import Component, ComponentStrategy, Ecosystem
from dr_environment.recipe.validate import (
    ValidationError,
    inspect_component,
    validate_all,
    validate_component,
)


def _component(tmp_path: Path, name: str = "agent") -> Component:
    comp_dir = tmp_path / name
    comp_dir.mkdir()
    return Component(name=name, source_dir=comp_dir, strategy=ComponentStrategy.DEFAULT)


def test_stale_uv_lock_detected_by_uv_lock_check(tmp_path: Path) -> None:
    component = _component(tmp_path)
    (component.source_dir / "pyproject.toml").write_text("[project]\nname='x'\n")
    (component.source_dir / "uv.lock").write_text("lock")

    with patch("dr_environment.recipe.validate.subprocess.run") as run:
        run.return_value.returncode = 1
        infos = inspect_component(component)

    assert infos[0].ecosystem == Ecosystem.PYTHON
    assert infos[0].status.value == "stale"
    # `--check` is what makes this a check: plain `uv lock` would rewrite the lockfile and
    # report success, so validation could never fail again.
    assert run.call_args.args[0] == ["uv", "lock", "--check"]


def test_a_missing_validation_tool_points_at_its_installer(tmp_path: Path) -> None:
    """The path a contributor without npm hits; a bare FileNotFoundError is not actionable."""
    component = _component(tmp_path, "frontend")
    (component.source_dir / "package.json").write_text('{"name":"x"}')
    (component.source_dir / "package-lock.json").write_text("{}")

    with patch("dr_environment.recipe.validate.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(ValidationError) as exc:
            validate_component(component)

    message = "\n".join(exc.value.errors)
    assert "'npm' is required" in message
    assert "https://nodejs.org/en/download" in message


def test_a_stale_npm_lockfile_names_npms_own_tool(tmp_path: Path) -> None:
    component = _component(tmp_path, "other")
    (component.source_dir / "package.json").write_text('{"name":"x"}')
    (component.source_dir / "package-lock.json").write_text("")

    with patch("dr_environment.recipe.validate.subprocess.run") as run:
        run.return_value.returncode = 1
        with pytest.raises(ValidationError) as exc:
            validate_component(component)

    errors = "\n".join(exc.value.errors)
    assert "out-of-date package-lock.json" in errors
    # The fix line is the ecosystem's own command, not whichever is first in MANIFEST_SPECS.
    assert "Fix: cd other && npm install" in errors


def test_each_manifest_is_checked_once_per_build(tmp_path: Path) -> None:
    """`npm ci --dry-run` is the slowest part of a build, so the status inspect_component
    resolved is the one reported rather than being re-derived by a second pass.
    """
    component = _component(tmp_path, "frontend")
    (component.source_dir / "package.json").write_text('{"name":"x"}')
    (component.source_dir / "package-lock.json").write_text("")

    with patch("dr_environment.recipe.validate.subprocess.run") as run:
        run.return_value.returncode = 1
        with pytest.raises(ValidationError):
            validate_component(component)

    assert run.call_args.args[0] == ["npm", "ci", "--dry-run", "--ignore-scripts"]
    assert run.call_count == 1


def test_validate_all_reports_every_broken_component_not_just_the_first(tmp_path: Path) -> None:
    """One run has to list them all, or a recipe is fixed one `dr environment` call at a time."""
    components = []
    for name in ("agent", "core"):
        component = _component(tmp_path, name)
        (component.source_dir / "pyproject.toml").write_text("[project]\nname='x'\n")
        components.append(component)

    with pytest.raises(ValidationError) as exc:
        validate_all(components)

    assert len(exc.value.errors) == 2
    assert "component 'agent'" in exc.value.errors[0]
    assert "component 'core'" in exc.value.errors[1]
