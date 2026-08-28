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
"""The entrypoint DataRobot runs for every deployed model.

`start_server_custom_model.sh` is COPY'd to /opt/code/start_server.sh and shipped into the
image. CI lints its syntax with shellcheck; this runs it, with `uv`, `nat` and `python` stubbed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from dr_environment.recipe.render import template_root

ENTRYPOINT = template_root() / "kernel" / "start_server_custom_model.sh"

STUBS = {
    # `uv venv` has to leave behind the activate script the entrypoint sources next.
    "uv": """#!/bin/sh
case "$1" in
  venv) mkdir -p "$2/bin"; : > "$2/bin/activate" ;;
  sync) echo "sync UV_NO_CACHE=${UV_NO_CACHE-unset}" >> "$RECORD" ;;
esac
exit 0
""",
    "nat": """#!/bin/sh
echo "nat $*" >> "$RECORD"
exit 0
""",
    # `-c` is the worker-count probe; anything else is the MCP dispatch.
    "python": """#!/bin/sh
if [ "$1" = "-c" ]; then echo 3; else echo "python $*" >> "$RECORD"; fi
exit 0
""",
}


def _run(
    tmp_path: Path,
    *,
    entry: str | None,
    offline: bool,
    url_prefix: str = "",
    expect_exit: int = 0,
) -> tuple[str, str]:
    code_dir = tmp_path / "code"
    code_dir.mkdir()
    script = code_dir / "start_server.sh"
    shutil.copy(ENTRYPOINT, script)
    script.chmod(0o755)
    if entry == "workflow":
        (code_dir / "workflow.yaml").write_text("workflow: {}\n", encoding="utf-8")
    elif entry == "app":
        (code_dir / "app").mkdir()

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in STUBS.items():
        stub = bin_dir / name
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)

    record = tmp_path / "record"
    env = os.environ.copy()
    for name in ("UV_NO_CACHE", "UV_OFFLINE", "URL_PREFIX"):
        env.pop(name, None)
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "RECORD": str(record),
            "VENV_DIR": str(tmp_path / "venv"),
            "UV_CACHE_DIR": str(tmp_path / "cache"),
        }
    )
    if offline:
        env["UV_OFFLINE"] = "1"
    if url_prefix:
        env["URL_PREFIX"] = url_prefix

    # By path, not `sh <script>`: the image chmods this file and execs it, so the shebang
    # is what selects the interpreter in production.
    result = subprocess.run([str(script)], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == expect_exit, result.stderr
    return result.stdout, record.read_text(encoding="utf-8") if record.is_file() else ""


@pytest.mark.parametrize(
    ("offline", "expected"),
    [(True, "sync UV_NO_CACHE=unset"), (False, "sync UV_NO_CACHE=1")],
)
def test_the_baked_cache_is_used_only_in_an_air_gapped_image(
    tmp_path: Path, offline: bool, expected: str
) -> None:
    """`UV_NO_CACHE=1` would make `uv sync` ignore the wheels baked into the image, and under
    UV_OFFLINE there is no index for a boot-time install to fall back to.
    """
    _, recorded = _run(tmp_path, entry="workflow", offline=offline)

    assert expected in recorded


def test_a_workflow_yaml_starts_the_agent_under_gunicorn(tmp_path: Path) -> None:
    _, recorded = _run(tmp_path, entry="workflow", offline=True)

    assert "nat dragent serve" in recorded
    assert "--use_gunicorn true" in recorded
    # DataRobot health-checks this address; binding elsewhere fails every deployment.
    assert "--host 0.0.0.0 --port 8080" in recorded
    # The stub answers 3 where the script's own default is 1, so a hardcoded count fails.
    assert "--workers 3" in recorded
    assert "workflow.yaml" in recorded
    assert "--root_path" not in recorded, "an unset URL_PREFIX must not reach the server"


def test_a_url_prefix_reaches_the_agent_as_its_root_path(tmp_path: Path) -> None:
    """A DataRobot deployment mounts every route below URL_PREFIX; without it they all 404."""
    _, recorded = _run(tmp_path, entry="workflow", offline=True, url_prefix="/deploy/abc")

    assert "--root_path /deploy/abc" in recorded


def test_an_app_directory_starts_the_mcp_server(tmp_path: Path) -> None:
    _, recorded = _run(tmp_path, entry="app", offline=True)

    assert "python -m app.main" in recorded
    assert "nat dragent serve" not in recorded


def test_neither_entry_point_fails_with_a_readable_error(tmp_path: Path) -> None:
    stdout, _ = _run(tmp_path, entry=None, offline=True, expect_exit=1)

    assert "No valid entry point found" in stdout
