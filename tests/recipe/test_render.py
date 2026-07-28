from pathlib import Path

from dr_environment.recipe.render import (
    assemble_dockerfile,
    copy_fragment_assets,
    render_build_deps_fragment,
    render_kernel_setup_fragment,
    render_offline_fragment,
    render_user_fragment,
    render_versions_fragment,
)
from dr_environment.recipe.versions import parse_tool_versions


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
    assert "UV_VERSION=\"0.9.0\"" in content
    assert "taskfile.dev/install.sh" in content
    assert "v3.43.3" in content
    assert "node-v24.0.0-linux-x64.tar.xz" in content
    assert "dr_v0.2.76_Linux_x86_64.tar.gz" in content
    assert "PULUMI_VERSION=3.206.0" in content
    assert "get.pulumi.com" in content
    assert "opencode.ai/install" in content
    assert "OPENCODE_VERSION=1.17.11" in content
    assert "uv tool install \"copier==9.17.0\"" in content
    assert "datarobot_early_access[core]>=3.17" in content
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
    assert 'UV_CACHE_DIR="${UV_CACHE_DIR}" uv pip install -r /tmp/build-deps/build-requirements.txt' in content
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
    assert "COPY --from=cache-agent --chown=notebooks:notebooks /opt/cache/uv /opt/cache/uv" in content
    assert "COPY --from=cache-agent --chown=notebooks:notebooks /opt/cache/npm /opt/cache/npm" in content
    assert "COPY --from=cache-agent --chown=notebooks:notebooks /opt/cache/go /opt/cache/go" in content
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
    assert tools.datarobot_early_access == "3.17"
