"""Copy component manifests into docker context."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from dr_environment.recipe.models import Component, ComponentStrategy, Ecosystem

# Recipe convention: sibling `core/` is a symlinked local shared Python package.
LOCAL_SHARED_PACKAGE = "core"

COPY_MAP: dict[Ecosystem, tuple[str, ...]] = {
    Ecosystem.PYTHON: ("pyproject.toml", "uv.lock"),
    Ecosystem.NPM: ("package.json", "package-lock.json"),
    Ecosystem.GO: ("go.mod", "go.sum"),
}


def strip_local_shared_python_package(pyproject_text: str) -> str:
    """Remove the symlinked local `core` package from a copied pyproject.toml."""
    text = re.sub(
        rf'^{LOCAL_SHARED_PACKAGE} = \{{ path = "{LOCAL_SHARED_PACKAGE}"[^\n]*\n',
        "",
        pyproject_text,
        flags=re.MULTILINE,
    )

    def _clean_inline_deps(match: re.Match[str]) -> str:
        inner = match.group(1)
        parts = [part.strip().strip('"') for part in inner.split(",") if part.strip()]
        kept = [part for part in parts if part != LOCAL_SHARED_PACKAGE]
        quoted = ", ".join(f'"{part}"' for part in kept)
        return f"dependencies = [{quoted}]"

    text = re.sub(
        r"^dependencies = \[(.*?)\]\s*$",
        _clean_inline_deps,
        text,
        flags=re.MULTILINE,
    )

    lines = text.splitlines()
    out: list[str] = []
    in_dependencies = False

    for line in lines:
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_dependencies = True
        elif in_dependencies and stripped == "]":
            in_dependencies = False
        elif in_dependencies and re.fullmatch(r'"core",?', stripped):
            continue
        out.append(line)

    trailing_newline = "\n" if pyproject_text.endswith("\n") else ""
    return "\n".join(out) + trailing_newline


def copy_component(component: Component, docker_context: Path) -> Path:
    """Copy manifest files for a component into components/<name>/."""
    dest = docker_context / "components" / component.dest_name
    dest.mkdir(parents=True, exist_ok=True)

    for info in component.manifests:
        manifest_dir = info.manifest.parent
        for filename in COPY_MAP[info.ecosystem]:
            src = manifest_dir / filename
            if not src.is_file():
                continue
            dest_file = dest / filename
            if (
                info.ecosystem == Ecosystem.PYTHON
                and filename == "pyproject.toml"
                and component.name != LOCAL_SHARED_PACKAGE
            ):
                dest_file.write_text(
                    strip_local_shared_python_package(src.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )
            else:
                shutil.copy2(src, dest_file)

    return dest


def layout_components(components: list[Component], docker_context: Path) -> None:
    for component in components:
        if component.strategy != ComponentStrategy.DEFAULT:
            continue
        if not component.manifests:
            continue
        copy_component(component, docker_context)
