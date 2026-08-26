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
from importlib.metadata import version

from click.testing import CliRunner

from dr_environment.cli import cli


def test_cli_help_lists_recipe_command() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "recipe" in result.output


def test_recipe_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["recipe", "--help"])
    assert result.exit_code == 0
    assert "--recipe-path" in result.output
    assert "--target" in result.output
    assert "--no-tarball" in result.output


def test_version_reports_installed_metadata() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert version("dr-environment") in result.output
