from pathlib import Path
from unittest.mock import patch

import pytest

from dr_environment.models import Component, ComponentStrategy, Ecosystem
from dr_environment.validate import ValidationError, inspect_component, validate_component


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

    with patch("dr_environment.validate.subprocess.run") as run:
        run.return_value.returncode = 1
        infos = inspect_component(component)

    assert infos[0].ecosystem == Ecosystem.PYTHON
    assert infos[0].status.value == "stale"
