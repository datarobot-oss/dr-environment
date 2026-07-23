from pathlib import Path

from dr_environment.render import (
    assemble_dockerfile,
    copy_static_template,
    render_kernel_fragment,
    template_root,
)


def test_assemble_dockerfile_orders_fragments(tmp_path: Path) -> None:
    docker_context = tmp_path / "ctx"
    dockerfile_d = docker_context / "dockerfile.d"
    dockerfile_d.mkdir(parents=True)
    (dockerfile_d / "10-b.fragment").write_text("FROM b")
    (dockerfile_d / "00-a.fragment").write_text("FROM a")

    assemble_dockerfile(docker_context)
    content = (docker_context / "Dockerfile").read_text()
    assert content.index("FROM a") < content.index("FROM b")


def test_copy_static_template_includes_dockerfile_assets(tmp_path: Path) -> None:
    docker_context = tmp_path / "ctx"
    docker_context.mkdir()
    copy_static_template(docker_context)

    expected = [
        "agent/agent.py",
        "agent/cgroup_watchers.py",
        "jupyter_kernel_gateway_config.py",
        "start_server_codespaces.sh",
        "kernel.json",
        "ipython_config.py",
        "extensions/dataframe_formatter.py",
        "sshd_config",
        "setup-prompt.sh",
        "setup-ssh.sh",
        "common-user-limits.sh",
        "setup-venv.sh",
        "setup-caches.sh",
        "kernel/requirements.txt",
    ]
    for rel in expected:
        assert (docker_context / rel).is_file(), rel


def test_render_kernel_fragment_includes_pulumi_version(tmp_path: Path) -> None:
    docker_context = tmp_path / "ctx"
    (docker_context / "dockerfile.d").mkdir(parents=True)
    versions = {"pulumi": {"minimum-version": "3.206.0"}}

    render_kernel_fragment(docker_context, final_stage="base", versions=versions)

    content = (docker_context / "dockerfile.d" / "99-kernel.fragment").read_text()
    assert 'PULUMI_VERSION=3.206.0' in content
    assert 'get.pulumi.com' in content
    assert 'pulumi login --local' in content
