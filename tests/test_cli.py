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
