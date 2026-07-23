from pathlib import Path

from dr_environment.render import assemble_dockerfile, copy_static_template, template_root


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
        "run_agent.py",
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

    assert (template_root() / "static" / "run_agent.py").is_file()
