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
from dr_environment.recipe.validate import ValidationError, inspect_component, validate_component


def _component(tmp_path: Path, name: str = "agent") -> Component:
    comp_dir = tmp_path / name
    comp_dir.mkdir()
    return Component(name=name, source_dir=comp_dir, strategy=ComponentStrategy.DEFAULT)


def test_missing_uv_lock_fails(tmp_path: Path) -> None:
    component = _component(tmp_path)
    (component.source_dir / "pyproject.toml").write_text("[project]\nname='x'\n")

    with pytest.raises(ValidationError) as exc:
        validate_component(component)
    assert "uv.lock is missing" in exc.value.errors[0]


def test_stale_uv_lock_detected_by_uv_lock_check(tmp_path: Path) -> None:
    component = _component(tmp_path)
    (component.source_dir / "pyproject.toml").write_text("[project]\nname='x'\n")
    (component.source_dir / "uv.lock").write_text("lock")

    with patch("dr_environment.recipe.validate.subprocess.run") as run:
        run.return_value.returncode = 1
        infos = inspect_component(component)

    assert infos[0].ecosystem == Ecosystem.PYTHON
    assert infos[0].status.value == "stale"
