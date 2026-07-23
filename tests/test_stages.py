from pathlib import Path

from dr_environment.cache.stages import write_component_cache_fragment
from dr_environment.layout import LOCAL_SHARED_PACKAGE
from dr_environment.models import Component, ComponentStrategy, Ecosystem, ManifestInfo


def test_python_cache_fragment_uses_uv_pip_install(tmp_path: Path) -> None:
    component = Component(
        name="agent",
        source_dir=tmp_path,
        strategy=ComponentStrategy.DEFAULT,
        fragment_order=10,
        manifests=[
            ManifestInfo(
                ecosystem=Ecosystem.PYTHON,
                manifest=tmp_path / "pyproject.toml",
                lockfile=tmp_path / "uv.lock",
            )
        ],
    )
    docker_context = tmp_path / "ctx"
    write_component_cache_fragment(component, docker_context, previous_stage="base")

    content = (docker_context / "dockerfile.d" / "10-cache-agent.fragment").read_text()
    assert "uv pip install" in content
    assert "uv pip download" not in content
    assert "--chown=notebooks:notebooks" in content
    assert "USER root" not in content
    assert "chown -R notebooks" not in content
    assert f"--no-emit-package {LOCAL_SHARED_PACKAGE}" in content
