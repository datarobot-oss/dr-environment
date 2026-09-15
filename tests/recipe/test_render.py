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
    assemble_dockerfile,
    copy_fragment_assets,
    render_build_deps_fragment,
    render_kernel_setup_fragment,
    render_offline_fragment,
    render_user_fragment,
    render_versions_fragment,
    template_root,
)
from dr_environment.recipe.versions import _DEFAULTS, parse_tool_versions


def test_assemble_dockerfile_orders_fragments(tmp_path: Path) -> None:
    docker_context = tmp_path / "ctx"
    dockerfile_d = docker_context / "dockerfile.d"
    dockerfile_d.mkdir(parents=True)
    (dockerfile_d / "10-b.fragment").write_text("FROM b")
    (dockerfile_d / "00-a.fragment").write_text("FROM a")

    assemble_dockerfile(docker_context)
    content = (docker_context / "Dockerfile").read_text()
    assert content.index("FROM a") < content.index("FROM b")


def test_copy_fragment_assets_includes_per_stage_files(tmp_path: Path) -> None:
    docker_context = tmp_path / "ctx"
    docker_context.mkdir()
    copy_fragment_assets(docker_context)

    expected = [
        "build-deps/build-requirements.txt",
        "kernel/requirements.txt",
        "kernel/agent/agent.py",
        "kernel/agent/cgroup_watchers.py",
        "kernel/jupyter_kernel_gateway_config.py",
        "kernel/start_server_codespaces.sh",
        "kernel/kernel.json",
        "kernel/ipython_config.py",
        "kernel/extensions/dataframe_formatter.py",
        "kernel/sshd_config",
        "kernel/setup-prompt.sh",
        "kernel/notebooks-path.sh",
        "kernel/setup-ssh.sh",
        "kernel/common-user-limits.sh",
        "kernel/setup-venv.sh",
        "kernel/setup-caches.sh",
    ]
    for rel in expected:
        assert (docker_context / rel).is_file(), rel


def test_render_user_fragment(tmp_path: Path) -> None:
    docker_context = tmp_path / "ctx"
    (docker_context / "dockerfile.d").mkdir(parents=True)

    render_user_fragment(docker_context)

    content = (docker_context / "dockerfile.d" / "01-user.fragment").read_text()
    assert "FROM base AS user" in content
    assert "adduser" in content
    assert "USER $UNAME" in content
    assert "HOME=/home/notebooks" in content


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
    assert "astral.sh/uv/install.sh" in content
    assert 'UV_VERSION="0.9.0"' in content
    assert "taskfile.dev/install.sh" in content
    assert "v3.43.3" in content
    assert "node-v24.0.0-linux-x64.tar.xz" in content
    assert "dr_v0.2.76_Linux_x86_64.tar.gz" in content
    assert "PULUMI_VERSION=3.206.0" in content
    assert "get.pulumi.com" in content
    assert "opencode.ai/install" in content
    assert "OPENCODE_VERSION=1.17.11" in content
    assert 'uv tool install "copier==9.17.0"' in content
    assert "datarobot[core]>=3.19.0" in content
    assert 'pulumi plugin install resource datarobot "$PULUMI_DATAROBOT_VERSION"' in content
    assert "--server github://api.github.com/datarobot-community/pulumi-datarobot" in content
    assert "PULUMI_DATAROBOT_VERSION=v0.10.43" in content
    assert 'pulumi plugin install resource command "$PULUMI_COMMAND_VERSION"' in content
    assert "PULUMI_COMMAND_VERSION=v1.2.1" in content
    assert "plugin install xp" in content
    assert "pulumi login --local" in content
    assert "PULUMI_SKIP_UPDATE_CHECK" not in content
    assert "chown" not in content


def test_render_build_deps_fragment_warms_pep517_build_deps(tmp_path: Path) -> None:
    docker_context = tmp_path / "ctx"
    (docker_context / "dockerfile.d").mkdir(parents=True)

    render_build_deps_fragment(docker_context)

    content = (docker_context / "dockerfile.d" / "03-build-deps.fragment").read_text()
    assert "FROM versions AS build-deps" in content
    assert "COPY --chown=${UNAME}:${UNAME} build-deps/build-requirements.txt" in content
    assert "USER root" not in content
    assert (
        'UV_CACHE_DIR="${UV_CACHE_DIR}" uv pip install -r /tmp/build-deps/build-requirements.txt'
        in content
    )
    assert "/tmp/build-deps-venv/bin/python" in content


def test_render_kernel_setup_fragment(tmp_path: Path) -> None:
    docker_context = tmp_path / "ctx"
    (docker_context / "dockerfile.d").mkdir(parents=True)

    render_kernel_setup_fragment(docker_context)

    content = (docker_context / "dockerfile.d" / "04-kernel.fragment").read_text()
    assert "FROM build-deps AS kernel" in content
    assert "VENV_PATH" in content
    assert "uv venv" in content
    assert "uv pip install" in content
    assert "build-requirements.txt" not in content
    assert "python -m venv" not in content
    assert "/bin/pip" not in content
    assert "kernel.json" in content
    assert "COPY kernel/agent/agent.py" in content
    assert "COPY kernel/setup-ssh.sh" in content
    assert "adduser" not in content
    assert "PYTHONUNBUFFERED" not in content
    assert "UV_OFFLINE" not in content
    assert "EXPOSE 8888" in content
    assert "notebooks-load-env.sh" in content
    assert "bash-profile-load.sh" in content


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
    assert "UV_FIND_LINKS=/opt/wheelhouse" in content
    assert "UV_OFFLINE=1" in content
    assert "NOTEBOOKS_NO_PERSISTENT_DEPENDENCIES=1" in content
    assert "DEEPEVAL_HOME=/tmp/.deepeval" in content
    assert "GOPROXY=off" in content


def test_render_offline_fragment_without_cache_stages(tmp_path: Path) -> None:
    docker_context = tmp_path / "ctx"
    (docker_context / "dockerfile.d").mkdir(parents=True)

    render_offline_fragment(docker_context, cache_stage=None)

    content = (docker_context / "dockerfile.d" / "99-offline.fragment").read_text()
    assert "FROM kernel AS offline" in content
    assert "COPY --from=" not in content


def test_parse_tool_versions_defaults() -> None:
    tools = parse_tool_versions({})
    assert tools.dr == "v0.2.76"
    assert tools.uv == "0.9.0"
    assert tools.node == "v24.0.0"
    assert tools.pulumi == "3.163.0"
    assert tools.opencode == "1.17.11"
    assert tools.copier == "9.17.0"
    assert tools.datarobot == "3.19.0"
    assert tools.pulumi_datarobot == "v0.10.43"
    assert tools.pulumi_command == "v1.2.1"


def test_fragment_license_headers_are_jinja_comments_and_never_reach_the_dockerfile() -> None:
    # Every fragment must carry the Apache header so the .j2 is licensed like any other
    # source file, but as a Jinja comment `{# ... -#}` so it is stripped at render time.
    # A plain `#` header would still satisfy license-eye while leaking 14 lines of
    # boilerplate into every customer's generated Dockerfile.
    fragments = sorted(template_root().glob("*.fragment.j2"))
    assert fragments, "no Dockerfile fragments found"

    for fragment in fragments:
        source = fragment.read_text(encoding="utf-8")
        assert source.startswith("{#"), f"{fragment.name} header must open a Jinja comment"
        assert "Apache License" in source, f"{fragment.name} is missing the license header"
        header, _, _ = source.partition("-#}")
        assert "Apache License" in header, (
            f"{fragment.name} has the license text outside the Jinja comment, "
            "so it would render into the Dockerfile"
        )
