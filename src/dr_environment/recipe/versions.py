"""Parse recipe .datarobot/cli/versions.yaml for Dockerfile rendering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolVersions:
    """Pinned tool versions from versions.yaml minimum-version fields."""

    dr: str
    uv: str
    node: str
    git: str
    task: str
    pulumi: str
    opencode: str
    copier: str
    datarobot_early_access: str


_DEFAULTS = {
    "dr": "0.2.76",
    "uv": "0.9.0",
    "node": "24.0.0",
    "git": "2.30.0",
    "task": "3.43.3",
    "pulumi": "3.163.0",
    "opencode": "1.17.11",
    "copier": "9.17.0",
    "datarobot_early_access": "3.17",
}


def _minimum_version(versions: dict, tool: str) -> str:
    raw = versions.get(tool, {}).get("minimum-version", _DEFAULTS[tool])
    return str(raw)


def _release_tag(version: str) -> str:
    return version if version.startswith("v") else f"v{version}"


def parse_tool_versions(versions: dict) -> ToolVersions:
    return ToolVersions(
        dr=_release_tag(_minimum_version(versions, "dr")),
        uv=_minimum_version(versions, "uv"),
        node=_release_tag(_minimum_version(versions, "node")),
        git=_minimum_version(versions, "git"),
        task=_minimum_version(versions, "task"),
        pulumi=_minimum_version(versions, "pulumi"),
        opencode=_minimum_version(versions, "opencode"),
        copier=_minimum_version(versions, "copier"),
        datarobot_early_access=_minimum_version(versions, "datarobot_early_access"),
    )
