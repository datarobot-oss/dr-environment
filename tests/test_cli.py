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
import json
from importlib.metadata import version
from pathlib import Path

import pytest
from click.testing import CliRunner

from dr_environment.cli import cli, main


def test_plugin_manifest_matches_the_dr_cli_contract(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `dr` CLI reads this to register the plugin, ahead of any click parsing."""
    monkeypatch.setattr("sys.argv", ["dr-environment", "--dr-plugin-manifest"])

    main()

    assert json.loads(capsys.readouterr().out) == {
        "name": "environment",
        "version": version("dr-environment"),
        "description": (
            "Build execution environment Docker contexts with offline dependency caches"
        ),
        "authentication": False,
    }


def test_recipe_command_writes_the_context_and_the_archive(recipe: Path, tmp_path: Path) -> None:
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["recipe", "--recipe-path", str(recipe)])

        assert result.exit_code == 0, result.output
        assert "Built docker context:" in result.output
        assert "Archive:" in result.output
        assert Path("docker_context/Dockerfile").is_file()
        assert Path("docker_context.tar.gz").is_file()


def test_recipe_command_skips_the_archive_when_asked(recipe: Path, tmp_path: Path) -> None:
    """The reported path used to be gated on the file existing rather than on the flag.

    A --no-tarball run in a reused directory then announced the previous run's stale archive.
    """
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path):
        # A sentinel rather than no file at all: a previous run's archive legitimately stays
        # on disk, and its survival is what proves this run neither wrote nor reported one.
        archive = Path("docker_context.tar.gz")
        archive.write_bytes(b"sentinel")

        result = runner.invoke(cli, ["recipe", "--recipe-path", str(recipe), "--no-tarball"])

        assert result.exit_code == 0, result.output
        assert "Archive:" not in result.output
        assert archive.read_bytes() == b"sentinel", "--no-tarball still wrote an archive"


def test_a_recipe_without_a_taskfile_exits_nonzero_with_a_readable_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["dr-environment", "recipe", "--recipe-path", str(tmp_path)])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    assert "No Taskfile.yml found" in capsys.readouterr().err
