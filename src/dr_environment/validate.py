"""Lockfile validation for component manifests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from dr_environment.models import (
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


class ValidationError(Exception):
    """Raised when a component fails lockfile validation."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def inspect_component(component: Component) -> list[ManifestInfo]:
    """Detect manifests and lockfile status without raising."""
    manifests: list[ManifestInfo] = []
    for manifest_name, lock_name, ecosystem, _fix in MANIFEST_SPECS:
        manifest = component.source_dir / manifest_name
        if not manifest.is_file():
            continue
        lockfile = component.source_dir / lock_name
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

    errors: list[str] = []
    manifests = inspect_component(component)

    if component.strategy == ComponentStrategy.DEFAULT and not manifests:
        return

    for manifest_name, lock_name, ecosystem, fix_cmd in MANIFEST_SPECS:
        manifest = component.source_dir / manifest_name
        if not manifest.is_file():
            continue
        lockfile = component.source_dir / lock_name
        status, message = _check_lockfile(manifest, lockfile, ecosystem)
        if status != LockfileStatus.OK:
            rel = component.source_dir.name
            errors.append(
                f"ERROR: component '{component.name}' {message}\n"
                f"  Fix: cd {rel} && {fix_cmd}"
            )

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
        result = subprocess.run(
            ["uv", "lock", "--check"],
            cwd=manifest.parent,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return LockfileStatus.STALE, "has out-of-date uv.lock (uv lock --check failed)"

    elif ecosystem == Ecosystem.NPM:
        result = subprocess.run(
            ["npm", "ci", "--dry-run", "--ignore-scripts"],
            cwd=manifest.parent,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return (
                LockfileStatus.STALE,
                "has out-of-date package-lock.json (npm ci --dry-run failed)",
            )

    elif ecosystem == Ecosystem.GO:
        result = subprocess.run(
            ["go", "mod", "verify"],
            cwd=manifest.parent,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return LockfileStatus.STALE, "has invalid go.sum (go mod verify failed)"

    return LockfileStatus.OK, ""
