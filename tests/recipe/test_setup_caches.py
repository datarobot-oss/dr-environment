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
"""The login-shell script that points a platform-injected template mirror at the baked clones."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from dr_environment.recipe.render import template_root

SCRIPT = template_root() / "kernel" / "setup-caches.sh"


def _source(tmp_path: Path, **env: str) -> None:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    subprocess.run(
        ["bash", "-c", f'source "{SCRIPT}"'],
        env={**os.environ, "HOME": str(home), **env},
        check=True,
        capture_output=True,
        text=True,
    )


def _insteadof(tmp_path: Path, clone: Path) -> list[str]:
    result = subprocess.run(
        ["git", "config", "--global", "--get-all", f"url.file://{clone}.insteadOf"],
        env={**os.environ, "HOME": str(tmp_path / "home")},
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.split()


def test_a_platform_mirror_url_is_redirected_to_each_baked_clone(tmp_path: Path) -> None:
    baked = tmp_path / "templates"
    (baked / "af-component-agent.git").mkdir(parents=True)
    (baked / "notes.txt").write_text("not a clone", encoding="utf-8")

    # Sourced twice, as two logins would: no accumulated duplicates.
    for _ in range(2):
        _source(
            tmp_path,
            BAKED_TEMPLATES=str(baked),
            APPLICATION_TEMPLATE_GIT_BASE_URL="http://minio.svc:9000/",
        )

    # The rewrite keeps the origin's suffix, so both shapes redirect.
    assert _insteadof(tmp_path, baked / "af-component-agent.git") == [
        "http://minio.svc:9000/af-component-agent.git",
        "http://minio.svc:9000/af-component-agent",
    ]


def test_without_a_platform_mirror_nothing_is_written(tmp_path: Path) -> None:
    baked = tmp_path / "templates"
    (baked / "af-component-agent.git").mkdir(parents=True)

    _source(tmp_path, BAKED_TEMPLATES=str(baked))

    assert _insteadof(tmp_path, baked / "af-component-agent.git") == []
