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

    Generated, not committed: a lockfile from another uv or npm fails its ecosystem's check.
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


def _install_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, body: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / name
    stub.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    stub.chmod(0o755)
    # Prepended so the stub wins over the real tool.
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


@pytest.fixture
def stub_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    """Put a `task` on PATH running the given shell body, so go-task is not needed."""

    def install(body: str) -> None:
        _install_stub(tmp_path, monkeypatch, "task", body)

    return install


@pytest.fixture
def template_repo(tmp_path: Path) -> Path:
    """Create a tagged git repo with a copier.yml of three frameworks."""
    repo = tmp_path / "af-component-agent"
    repo.mkdir()
    (repo / "copier.yml").write_text(
        "agent_template_framework:\n  type: str\n  choices:\n"
        "    Base: base\n    CrewAI: crewai\n    NAT: nat\n",
        encoding="utf-8",
    )
    for args in (
        ("init", "-q"),
        ("add", "copier.yml"),
        (
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.com",
            "commit",
            "-q",
            "-m",
            "init",
        ),
        ("tag", "1.0.0"),
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return repo


@pytest.fixture
def agent_recipe(recipe: Path, template_repo: Path) -> Path:
    """Mark the fixture recipe's agent_app as an af-component-agent render."""
    pyproject = recipe / "agent" / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8") + '\n[tool.af-component]\ntype = "agent"\n',
        encoding="utf-8",
    )
    answers = recipe / ".datarobot" / "answers"
    answers.mkdir()
    (answers / "agent-agent.yml").write_text(
        f"_commit: 1.0.0\n_src_path: {template_repo}\nagent_app_name: agent\n"
        "agent_template_framework: base\nuse_agent_memory: none\nuse_low_code_interface: true\n",
        encoding="utf-8",
    )
    return recipe


@pytest.fixture
def stub_uvx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fake `uvx copier copy`: renders and locks the fixture manifest, crewai with a different
    lock. Returns the argv record. Knobs: UVX_FAIL, UVX_STALE, UVX_IGNORE_FRAMEWORK.
    """
    record = tmp_path / "uvx-record"
    fixture_pyproject = (FIXTURE_RECIPE / "agent" / "pyproject.toml").read_text(encoding="utf-8")
    _install_stub(
        tmp_path,
        monkeypatch,
        "uvx",
        f'echo "argv $*" >> "{record}"\n'
        "app=agent\n"
        'for arg in "$@"; do\n'
        '  case "$arg" in\n'
        '    agent_template_framework=*) framework="${arg#*=}";;\n'
        '    agent_app_name=*) app="${arg#*=}";;\n'
        "  esac\n"
        '  dest="$arg"\n'
        "done\n"
        '[ "$framework" = "${UVX_FAIL:-}" ] && { echo "copier: boom" >&2; exit 1; }\n'
        'mkdir -p "$dest/$app"\n'
        f"cat > \"$dest/$app/pyproject.toml\" <<'PYPROJECT'\n{fixture_pyproject}PYPROJECT\n"
        '[ "$framework" = crewai ] && sed -i.bak \'s/>=3.11/>=3.12/\' "$dest/$app/pyproject.toml"\n'
        '(cd "$dest/$app" && uv lock -q)\n'
        # Copier writes the answers it used; a hidden question would leave the recipe's value.
        '[ -n "${UVX_IGNORE_FRAMEWORK:-}" ] || printf "agent_app_name: %s\\nagent_template_framework: %s\\n" '
        '"$app" "$framework" > "$dest/.datarobot/answers/agent-$app.yml"\n'
        '[ "$framework" = "${UVX_STALE:-}" ] && sed -i.bak \'s/>=3.1[12]/>=3.13/\' "$dest/$app/pyproject.toml"\n'
        "exit 0",
    )
    return record
