"""Invoke component Taskfile environment hooks."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from dr_environment.discover import find_taskfile
from dr_environment.models import Component


def run_environment_hook(component: Component, docker_context: Path) -> None:
    """Run `task environment` with the documented env contract."""
    taskfile = find_taskfile(component.source_dir)
    if taskfile is None:
        raise FileNotFoundError(f"No Taskfile for component {component.name}")

    fragment_path = (
        docker_context
        / "dockerfile.d"
        / f"{component.fragment_order:02d}-cache-{component.name}.fragment"
    )
    fragment_path.parent.mkdir(parents=True, exist_ok=True)
    if not fragment_path.exists():
        fragment_path.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "DOCKER_CONTEXT": str(docker_context.resolve()),
            "COMPONENT_DIR": str(component.source_dir.resolve()),
            "COMPONENT_NAME": component.name,
            "DOCKERFILE_FRAGMENT": str(fragment_path.resolve()),
            "COMPONENT_DEST": str(
                (docker_context / "components" / component.name).resolve()
            ),
        }
    )

    subprocess.run(
        ["task", "-d", str(component.source_dir), "environment"],
        env=env,
        check=True,
    )
