"""Render docker context from templates and fragments."""

from __future__ import annotations

import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from dr_environment.recipe.cache.stages import CACHE_COPY_PATHS
from dr_environment.recipe.versions import parse_tool_versions

# Asset directories copied into docker_context; names match Dockerfile fragment stages.
FRAGMENT_ASSET_DIRS = ("build-deps", "kernel")


def template_root() -> Path:
    return Path(__file__).resolve().parent / "templates" / "docker_context"


def copy_fragment_assets(docker_context: Path) -> None:
    """Copy per-fragment asset trees into the generated docker context."""
    root = template_root()
    for name in FRAGMENT_ASSET_DIRS:
        src = root / name
        if not src.is_dir():
            continue
        shutil.copytree(src, docker_context / name)


# Backward-compatible alias for tests and callers.
copy_static_template = copy_fragment_assets


def render_base_fragment(docker_context: Path) -> None:
    env = _jinja_env()
    template = env.get_template("00-base.fragment.j2")
    content = template.render(
        uv_cache_dir="/opt/cache/uv",
        python_version="3.11",
        target_platform="linux/amd64",
    )
    dockerfile_d = docker_context / "dockerfile.d"
    dockerfile_d.mkdir(parents=True, exist_ok=True)
    (dockerfile_d / "00-base.fragment").write_text(content, encoding="utf-8")


def render_user_fragment(docker_context: Path) -> None:
    env = _jinja_env()
    template = env.get_template("01-user.fragment.j2")
    content = template.render()
    dockerfile_d = docker_context / "dockerfile.d"
    (dockerfile_d / "01-user.fragment").write_text(content, encoding="utf-8")


def render_versions_fragment(docker_context: Path, versions: dict) -> None:
    env = _jinja_env()
    template = env.get_template("02-versions.fragment.j2")
    tools = parse_tool_versions(versions)
    content = template.render(
        dr_version=tools.dr,
        uv_version=tools.uv,
        node_version=tools.node,
        git_version=tools.git,
        task_version=tools.task,
        pulumi_version=tools.pulumi,
        opencode_version=tools.opencode,
        copier_version=tools.copier,
        datarobot_version=tools.datarobot,
        pulumi_datarobot_version=tools.pulumi_datarobot,
        pulumi_command_version=tools.pulumi_command,
    )
    dockerfile_d = docker_context / "dockerfile.d"
    (dockerfile_d / "02-versions.fragment").write_text(content, encoding="utf-8")


def render_build_deps_fragment(docker_context: Path) -> None:
    env = _jinja_env()
    template = env.get_template("03-build-deps.fragment.j2")
    content = template.render()
    dockerfile_d = docker_context / "dockerfile.d"
    (dockerfile_d / "03-build-deps.fragment").write_text(content, encoding="utf-8")


def render_kernel_setup_fragment(docker_context: Path) -> None:
    env = _jinja_env()
    template = env.get_template("04-kernel.fragment.j2")
    content = template.render()
    dockerfile_d = docker_context / "dockerfile.d"
    (dockerfile_d / "04-kernel.fragment").write_text(content, encoding="utf-8")


def render_offline_fragment(docker_context: Path, *, cache_stage: str | None) -> None:
    env = _jinja_env()
    template = env.get_template("99-offline.fragment.j2")
    content = template.render(
        cache_stage=cache_stage,
        cache_copy_paths=CACHE_COPY_PATHS,
    )
    dockerfile_d = docker_context / "dockerfile.d"
    (dockerfile_d / "99-offline.fragment").write_text(content, encoding="utf-8")


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
