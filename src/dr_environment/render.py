"""Render docker context from templates and fragments."""

from __future__ import annotations

import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


def template_root() -> Path:
    return Path(__file__).resolve().parent / "templates" / "docker_context"


def copy_static_template(docker_context: Path) -> None:
    static = template_root() / "static"
    if static.is_dir():
        for item in static.iterdir():
            dest = docker_context / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

    kernel_req = template_root() / "kernel" / "requirements.txt"
    kernel_dest = docker_context / "kernel"
    kernel_dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(kernel_req, kernel_dest / "requirements.txt")


def render_base_fragment(docker_context: Path, versions: dict) -> None:
    env = _jinja_env()
    template = env.get_template("00-base.fragment.j2")
    cli_version = versions.get("dr", {}).get("minimum-version", "0.2.76")
    if not str(cli_version).startswith("v"):
        cli_version = f"v{cli_version}"
    content = template.render(
        cli_version=cli_version,
        opencode_version="1.17.11",
        uv_cache_dir="/opt/cache/uv",
        python_version="3.12",
    )
    dockerfile_d = docker_context / "dockerfile.d"
    dockerfile_d.mkdir(parents=True, exist_ok=True)
    (dockerfile_d / "00-base.fragment").write_text(content, encoding="utf-8")


def render_kernel_fragment(docker_context: Path, *, final_stage: str) -> None:
    env = _jinja_env()
    template = env.get_template("99-kernel.fragment.j2")
    content = template.render(final_stage=final_stage)
    dockerfile_d = docker_context / "dockerfile.d"
    (dockerfile_d / "99-kernel.fragment").write_text(content, encoding="utf-8")


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(template_root())),
        autoescape=select_autoescape(enabled_extensions=()),
        keep_trailing_newline=True,
    )


def assemble_dockerfile(docker_context: Path) -> None:
    dockerfile_d = docker_context / "dockerfile.d"
    parts: list[str] = []
    for fragment in sorted(dockerfile_d.glob("*.fragment")):
        parts.append(fragment.read_text(encoding="utf-8").rstrip())
        parts.append("")
    (docker_context / "Dockerfile").write_text("\n".join(parts), encoding="utf-8")
