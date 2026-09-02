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
from pathlib import Path

import pytest

from dr_environment.recipe.render import (
    copy_fragment_assets,
    render_base_fragment,
    render_offline_fragment,
    render_versions_fragment,
    template_root,
)
from dr_environment.recipe.versions import _DEFAULTS


def test_local_bytecode_is_not_copied_into_the_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Byte-code from a local lint run must not be baked into the image."""
    templates = tmp_path / "templates"
    (templates / "kernel" / "__pycache__").mkdir(parents=True)
    (templates / "kernel" / "__pycache__" / "render.pyc").write_bytes(b"")
    monkeypatch.setattr("dr_environment.recipe.render.template_root", lambda: templates)

    copy_fragment_assets(tmp_path / "ctx")

    assert not (tmp_path / "ctx" / "kernel" / "__pycache__").exists()


def test_kernel_datarobot_pin_matches_versions_default() -> None:
    """The kernel venv pin must not fall below the floor the image installs the SDK from."""
    reqs = template_root() / "kernel" / "requirements.txt"
    pinned = next(
        line.split("==", 1)[1].strip()
        for line in reqs.read_text(encoding="utf-8").splitlines()
        if line.startswith("datarobot==")
    )
    default = _DEFAULTS["datarobot"]

    def parts(v: str) -> list[int]:
        return [int(x) for x in v.split(".") if x.isdigit()]

    assert parts(pinned)[: len(parts(default))] >= parts(default), (
        f"kernel requirements pin datarobot=={pinned}, "
        f"but versions.py installs datarobot>={default}"
    )


def test_render_versions_fragment_rejects_non_version_value(tmp_path: Path) -> None:
    docker_context = tmp_path / "ctx"
    (docker_context / "dockerfile.d").mkdir(parents=True)
    versions = {"uv": {"minimum-version": "0.9.0\nRUN echo injected"}}

    with pytest.raises(ValueError, match="invalid uv minimum-version"):
        render_versions_fragment(docker_context, versions)


def test_render_versions_fragment_installs_all_tools(tmp_path: Path) -> None:
    docker_context = tmp_path / "ctx"
    (docker_context / "dockerfile.d").mkdir(parents=True)
    versions = {
        "dr": {"minimum-version": "0.2.76"},
        "uv": {"minimum-version": "0.9.0"},
        "node": {"minimum-version": "24.0.0"},
        "git": {"minimum-version": "2.30.0"},
        "task": {"minimum-version": "3.43.3"},
        "pulumi": {"minimum-version": "3.206.0"},
    }

    render_versions_fragment(docker_context, versions)

    content = (docker_context / "dockerfile.d" / "02-versions.fragment").read_text()
    assert "FROM user AS versions" in content
    assert "USER $UNAME" in content
    # The versions above are interpolated, so each literal proves its own value was read.
    assert "astral.sh/uv/install.sh" in content
    assert 'UV_VERSION="0.9.0"' in content
    assert "taskfile.dev/install.sh" in content
    assert "v3.43.3" in content
    assert "node-v24.0.0-linux-x64.tar.xz" in content
    assert "dr_v0.2.76_Linux_x86_64.tar.gz" in content
    assert "PULUMI_VERSION=3.206.0" in content
    assert "get.pulumi.com" in content
    # The rest have no versions.yaml key, so they fall back to _DEFAULTS. Asserted against
    # _DEFAULTS rather than a literal: bumping a default is maintenance, not a regression.
    assert "opencode.ai/install" in content
    assert f"OPENCODE_VERSION={_DEFAULTS['opencode']}" in content
    assert f'uv tool install "copier=={_DEFAULTS["copier"]}"' in content
    assert f"datarobot[core]>={_DEFAULTS['datarobot']}" in content
    assert 'pulumi plugin install resource datarobot "$PULUMI_DATAROBOT_VERSION"' in content
    assert "--server github://api.github.com/datarobot-community/pulumi-datarobot" in content
    assert f"PULUMI_DATAROBOT_VERSION=v{_DEFAULTS['pulumi_datarobot']}" in content
    assert 'pulumi plugin install resource command "$PULUMI_COMMAND_VERSION"' in content
    assert f"PULUMI_COMMAND_VERSION=v{_DEFAULTS['pulumi_command']}" in content
    assert "plugin install xp" in content
    assert "pulumi login --local" in content


def test_render_offline_fragment_copies_caches_from_cache_stage(tmp_path: Path) -> None:
    docker_context = tmp_path / "ctx"
    (docker_context / "dockerfile.d").mkdir(parents=True)

    render_offline_fragment(docker_context, cache_stage="cache-agent")

    content = (docker_context / "dockerfile.d" / "99-offline.fragment").read_text()
    assert "FROM kernel AS offline" in content
    # The uv cache is copied from the cache-perms stage (its root is chmod 0777 there so the
    # uid-1000 model can write lock/temp files); the rest come straight from the cache stage.
    assert (
        "COPY --from=cache-perms --chown=notebooks:notebooks /opt/cache/uv /opt/cache/uv" in content
    )
    assert (
        "COPY --from=cache-agent --chown=notebooks:notebooks /opt/cache/npm /opt/cache/npm"
        in content
    )
    # The cache and venv modes govern whether a deployed model (a different uid) can write to
    # them, so assert them: a wrong mode here breaks every generated image.
    assert "RUN chmod -R a+rwX /opt/cache/uv" in content
    assert "RUN chmod 0777 /opt/cache/uv" in content
    assert "chmod a+rwx /opt/venv" in content
    assert (
        "COPY --from=cache-agent --chown=notebooks:notebooks /opt/cache/go /opt/cache/go" in content
    )
    assert (
        "COPY --from=cache-agent --chown=notebooks:notebooks /opt/wheelhouse /opt/wheelhouse"
        in content
    )
    # The air-gap settings are asserted in test_build.py, against the assembled Dockerfile
    # with comments stripped; these two are not part of that contract.
    assert "NOTEBOOKS_NO_PERSISTENT_DEPENDENCIES=1" in content
    assert "DEEPEVAL_HOME=/tmp/.deepeval" in content


def test_render_offline_fragment_without_cache_stages(tmp_path: Path) -> None:
    docker_context = tmp_path / "ctx"
    (docker_context / "dockerfile.d").mkdir(parents=True)

    render_offline_fragment(docker_context, cache_stage=None)

    content = (docker_context / "dockerfile.d" / "99-offline.fragment").read_text()
    assert "FROM kernel AS offline" in content
    assert "COPY --from=" not in content


def test_render_base_fragment_pins_python_311_and_the_build_platform(tmp_path: Path) -> None:
    """Both pins shipped as outages: 3.12 crash-loops agents on uvloop, arm64 on exec format."""
    docker_context = tmp_path / "ctx"

    render_base_fragment(docker_context)
    fragment = (docker_context / "dockerfile.d" / "00-base.fragment").read_text(encoding="utf-8")

    assert "ARG PYTHON_VERSION=3.11" in fragment
    assert "ARG TARGETPLATFORM=linux/amd64" in fragment
    assert "FROM --platform=${TARGETPLATFORM}" in fragment
