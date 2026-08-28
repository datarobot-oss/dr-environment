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
"""Lockfile validation for component manifests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from dr_environment.recipe.manifests import find_manifest_file
from dr_environment.recipe.models import (
    Component,
    ComponentStrategy,
    Ecosystem,
    LockfileStatus,
    ManifestInfo,
)

MANIFEST_SPECS: tuple[tuple[str, str, Ecosystem, str], ...] = (
    ("pyproject.toml", "uv.lock", Ecosystem.PYTHON, "uv lock"),
    ("package.json", "package-lock.json", Ecosystem.NPM, "npm install"),
    ("go.mod", "go.sum", Ecosystem.GO, "go mod tidy"),
)

_FIX_COMMANDS = {ecosystem: fix for _, _, ecosystem, fix in MANIFEST_SPECS}

# Each ecosystem is validated with its own native tool, so a recipe pulls in whichever of these its
# components use. Point the user at the installer rather than leaking a bare FileNotFoundError.
TOOL_INSTALL_HINTS: dict[str, str] = {
    "uv": "https://docs.astral.sh/uv/getting-started/installation/",
    "npm": "https://nodejs.org/en/download",
    "go": "https://go.dev/dl/",
}


class ValidationError(Exception):
    """Raised when a component fails lockfile validation."""

    def __init__(self, errors: list[str]):
        """Collect the per-component validation failures into one exception."""
        self.errors = errors
        super().__init__("\n".join(errors))


def inspect_component(component: Component) -> list[ManifestInfo]:
    """Detect manifests and lockfile status; only a missing validation tool raises."""
    manifests: list[ManifestInfo] = []
    for manifest_name, lock_name, ecosystem, _fix in MANIFEST_SPECS:
        manifest = find_manifest_file(component.source_dir, manifest_name)
        if manifest is None:
            continue
        lockfile = manifest.parent / lock_name
        info = ManifestInfo(
            ecosystem=ecosystem,
            manifest=manifest,
            lockfile=lockfile if lockfile.is_file() else None,
        )
        info.status, info.message = _check_lockfile(manifest, lockfile, ecosystem)
        manifests.append(info)
    component.manifests = manifests
    return manifests


def validate_component(component: Component) -> None:
    """Validate lockfiles for a component; raise ValidationError on failure."""
    if component.strategy == ComponentStrategy.SKIP:
        return

    # Reuse the statuses inspect_component already resolved: re-deriving them here would run
    # every ecosystem's check a second time, and `npm ci --dry-run` is the slowest part of a build.
    errors = [
        f"ERROR: component '{component.name}' {info.message}\n"
        f"  Fix: cd {component.source_dir.name} && {_FIX_COMMANDS[info.ecosystem]}"
        for info in inspect_component(component)
        if info.status != LockfileStatus.OK
    ]
    if errors:
        raise ValidationError(errors)


def validate_all(components: list[Component]) -> None:
    errors: list[str] = []
    for component in components:
        try:
            validate_component(component)
        except ValidationError as exc:
            errors.extend(exc.errors)
    if errors:
        raise ValidationError(errors)


def _run_check(cmd: list[str], cwd: Path) -> int:
    """Run a lockfile check and return its exit code; raise if the tool is not installed."""
    tool = cmd[0]
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,  # the returncode is the signal we want, not an exception
        )
    except FileNotFoundError as exc:
        hint = TOOL_INSTALL_HINTS.get(tool)
        message = f"ERROR: '{tool}' is required to validate '{cwd.name}' but is not installed"
        if hint:
            message = f"{message}\n  Install: {hint}"
        raise ValidationError([message]) from exc
    return result.returncode


def _check_lockfile(
    manifest: Path,
    lockfile: Path,
    ecosystem: Ecosystem,
) -> tuple[LockfileStatus, str]:
    if not lockfile.is_file():
        return (
            LockfileStatus.MISSING,
            f"has {manifest.name} but {lockfile.name} is missing",
        )

    if ecosystem == Ecosystem.PYTHON:
        if _run_check(["uv", "lock", "--check"], manifest.parent) != 0:
            return LockfileStatus.STALE, "has out-of-date uv.lock (uv lock --check failed)"

    elif ecosystem == Ecosystem.NPM:
        if _run_check(["npm", "ci", "--dry-run", "--ignore-scripts"], manifest.parent) != 0:
            return (
                LockfileStatus.STALE,
                "has out-of-date package-lock.json (npm ci --dry-run failed)",
            )

    elif ecosystem == Ecosystem.GO:
        if _run_check(["go", "mod", "verify"], manifest.parent) != 0:
            return LockfileStatus.STALE, "has invalid go.sum (go mod verify failed)"

    return LockfileStatus.OK, ""
