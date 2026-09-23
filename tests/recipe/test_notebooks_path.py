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
"""The login-shell PATH script must leave the venv first and once: the recipe's app start
script strips one leading venv entry to reach the system python.
"""

from __future__ import annotations

import subprocess

from dr_environment.recipe.render import template_root

SCRIPT = template_root() / "kernel" / "notebooks-path.sh"
VENV_BIN = "/etc/system/kernel/.venv/bin"


def _path_after(initial: str) -> list[str]:
    result = subprocess.run(
        ["bash", "-c", f'source "{SCRIPT}"; printf "%s" "$PATH"'],
        env={"PATH": initial},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.split(":")


def test_the_image_path_is_left_with_one_leading_venv_entry() -> None:
    """Only .opencode/bin is missing from the image ENV; prepending just it demotes the venv."""
    inherited = f"{VENV_BIN}:/home/notebooks/.local/bin:/home/notebooks/.local/bin:/usr/bin:/bin"

    path = _path_after(inherited)

    assert path == [
        VENV_BIN,
        "/home/notebooks/.local/bin",
        "/home/notebooks/.opencode/bin",
        "/usr/bin",
        "/bin",
    ]


def test_a_reset_sshd_path_gets_the_tool_directories_in_front() -> None:
    path = _path_after("/usr/bin:/bin")

    assert path[:3] == [VENV_BIN, "/home/notebooks/.local/bin", "/home/notebooks/.opencode/bin"]
    assert path[3:] == ["/usr/bin", "/bin"]
