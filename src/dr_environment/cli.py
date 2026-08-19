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
"""CLI entrypoint for dr-environment plugin."""

from __future__ import annotations

import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import click

from dr_environment.recipe import build


def _package_version() -> str:
    try:
        return version("dr-environment")
    except PackageNotFoundError:
        return "0.0.0"


def print_manifest() -> None:
    manifest = {
        "name": "environment",
        "version": _package_version(),
        "description": "Build execution environment Docker contexts with offline dependency caches",
        "authentication": False,
    }
    print(json.dumps(manifest, indent=2))


@click.group()
def cli() -> None:
    """Build DataRobot execution environment Docker contexts."""


@cli.command("recipe")
@click.option(
    "--recipe-path",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Recipe root directory, defaults to the current working directory",
)
@click.option(
    "--target",
    default="docker_context",
    help="Output directory relative to the current working directory, defaults to docker_context",
)
@click.option("--no-tarball", is_flag=True, help="Skip docker_context.tar.gz creation")
def recipe_cmd(recipe_path: Path, target: str, no_tarball: bool) -> None:
    """Build the recipe Codespace execution environment docker context."""
    docker_context = build(
        recipe_path.resolve(),
        Path(target),
        tarball=not no_tarball,
    )
    click.echo(f"Built docker context: {docker_context}")
    archive = docker_context.parent / "docker_context.tar.gz"
    if archive.is_file():
        click.echo(f"Archive: {archive}")


def main() -> None:
    if "--dr-plugin-manifest" in sys.argv:
        print_manifest()
        return

    try:
        cli(prog_name="dr-environment")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
