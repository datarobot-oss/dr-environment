from pathlib import Path

from dr_environment.cache.stages import write_component_cache_fragment
from dr_environment.layout import LOCAL_SHARED_PACKAGE, copy_component, strip_local_shared_python_package
from dr_environment.models import Component, ComponentStrategy, Ecosystem, ManifestInfo


def test_strip_local_shared_python_package() -> None:
    pyproject = """[project]
dependencies = [
    "ag-ui-protocol>=0.1.9",
    "core",
    "datarobot[auth-authlib,core]>=3.9.1",
]

[tool.uv.sources]
core = { path = "core", editable = true }
other = { path = "vendor", editable = true }
"""
    stripped = strip_local_shared_python_package(pyproject)
    assert '\n    "core",\n' not in stripped
    assert "datarobot[auth-authlib,core]" in stripped
    assert 'core = { path = "core", editable = true }' not in stripped
    assert 'other = { path = "vendor", editable = true }' in stripped


def test_python_cache_fragment_omits_core_for_other_components(tmp_path: Path) -> None:
    component = Component(
        name="fastapi_server",
        source_dir=tmp_path,
        strategy=ComponentStrategy.DEFAULT,
        fragment_order=15,
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

    content = (docker_context / "dockerfile.d" / "15-cache-fastapi_server.fragment").read_text()
    assert f"--no-emit-package {LOCAL_SHARED_PACKAGE}" in content


def test_python_cache_fragment_keeps_core_for_core_component(tmp_path: Path) -> None:
    component = Component(
        name=LOCAL_SHARED_PACKAGE,
        source_dir=tmp_path,
        strategy=ComponentStrategy.DEFAULT,
        fragment_order=11,
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

    content = (docker_context / "dockerfile.d" / "11-cache-core.fragment").read_text()
    assert "--no-emit-package core" not in content


def test_copy_component_strips_core_from_pyproject(tmp_path: Path) -> None:
    component_dir = tmp_path / "fastapi_server"
    component_dir.mkdir()
    (component_dir / "pyproject.toml").write_text(
        '[project]\ndependencies = ["core"]\n\n[tool.uv.sources]\n'
        'core = { path = "core", editable = true }\n',
        encoding="utf-8",
    )
    (component_dir / "uv.lock").write_text("version = 1\n", encoding="utf-8")

    component = Component(
        name="fastapi_server",
        source_dir=component_dir,
        strategy=ComponentStrategy.DEFAULT,
    )
    component.manifests = [
        ManifestInfo(
            ecosystem=Ecosystem.PYTHON,
            manifest=component_dir / "pyproject.toml",
            lockfile=component_dir / "uv.lock",
        )
    ]

    docker_context = tmp_path / "ctx"
    copy_component(component, docker_context)
    copied = (docker_context / "components/fastapi_server/pyproject.toml").read_text()
    assert "core = { path" not in copied
    assert '"core"' not in copied

    core_component = Component(
        name=LOCAL_SHARED_PACKAGE,
        source_dir=tmp_path / LOCAL_SHARED_PACKAGE,
        strategy=ComponentStrategy.DEFAULT,
    )
    core_dir = tmp_path / LOCAL_SHARED_PACKAGE
    core_dir.mkdir()
    (core_dir / "pyproject.toml").write_text(
        '[project]\nname = "core"\ndependencies = ["httpx"]\n',
        encoding="utf-8",
    )
    (core_dir / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    core_component.manifests = [
        ManifestInfo(
            ecosystem=Ecosystem.PYTHON,
            manifest=core_dir / "pyproject.toml",
            lockfile=core_dir / "uv.lock",
        )
    ]
    copy_component(core_component, docker_context)
    core_copied = (docker_context / "components/core/pyproject.toml").read_text()
    assert 'name = "core"' in core_copied
