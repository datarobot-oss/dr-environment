from pathlib import Path

import yaml

from dr_environment.discover import discover_components
from dr_environment.models import ComponentStrategy


def test_discover_components_skips_internal_and_infra_only(tmp_path: Path) -> None:
    recipe = tmp_path / "recipe"
    recipe.mkdir()
    (recipe / "agent").mkdir()
    (recipe / "agent" / "pyproject.toml").write_text("[project]\nname='a'\n")
    (recipe / "agent" / "uv.lock").write_text("")

    taskfile = {
        "version": "3",
        "includes": {
            "common": {"taskfile": "./core/task-common.yaml", "internal": True},
            "agent": {"taskfile": "./agent/Taskfile.yml", "dir": "./agent"},
            "infra": {"taskfile": "./infra/Taskfile.yaml", "dir": "./infra"},
        },
    }
    (recipe / "Taskfile.yml").write_text(yaml.dump(taskfile))
    (recipe / "infra").mkdir()

    components = discover_components(recipe)
    names = [c.name for c in components]
    assert names == ["agent", "infra"]
    assert components[0].strategy == ComponentStrategy.DEFAULT
    assert components[1].strategy == ComponentStrategy.SKIP
