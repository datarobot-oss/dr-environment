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
"""Invoke component Taskfile environment hooks."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from dr_environment.recipe.discover import find_taskfile
from dr_environment.recipe.models import Component


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
            "COMPONENT_DEST": str((docker_context / "components" / component.name).resolve()),
        }
    )

    subprocess.run(
        ["task", "-d", str(component.source_dir), "environment"],
        env=env,
        check=True,
    )
