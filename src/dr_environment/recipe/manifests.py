"""Locate component manifest files within a component directory."""

from __future__ import annotations

from pathlib import Path

MANIFEST_NAMES = ("pyproject.toml", "package.json", "go.mod")

SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".git",
        "vendor",
    }
)


def find_manifest_file(component_dir: Path, manifest_name: str) -> Path | None:
    """Return the best manifest path, preferring the component root."""
    direct = component_dir / manifest_name
    if direct.is_file():
        return direct

    matches: list[Path] = []
    for path in component_dir.rglob(manifest_name):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(component_dir).parts[:-1]
        if any(part in SKIP_DIR_NAMES for part in rel_parts):
            continue
        matches.append(path)

    if not matches:
        return None

    matches.sort(key=lambda path: (len(path.relative_to(component_dir).parts), str(path)))
    return matches[0]


def has_any_manifest(component_dir: Path) -> bool:
    return any(find_manifest_file(component_dir, name) is not None for name in MANIFEST_NAMES)
