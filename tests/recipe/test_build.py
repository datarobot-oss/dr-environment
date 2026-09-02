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
"""End-to-end build of a docker context from a recipe."""

from __future__ import annotations

import re
import tarfile
from collections.abc import Callable
from pathlib import Path

import pytest

from dr_environment.recipe.build import build, create_tarball
from dr_environment.recipe.validate import ValidationError

# Every way one instruction can name an earlier stage: `COPY|ADD --from=`, `RUN --mount=,from=`.
# Unanchored, so a line carrying two mounts has both of its references checked.
_STAGE_REF = re.compile(r"\bfrom=([A-Za-z0-9_.-]+)", re.I)
_STAGE_DEF = re.compile(r"^FROM\s+(?:--\S+\s+)*\S+\s+AS\s+(\S+)", re.MULTILINE | re.I)
# Flags and sources of one COPY; every argument but the last is a source.
_COPY = re.compile(r"^COPY\s+((?:--\S+\s+)*)(.+)$", re.MULTILINE)

# Set in the offline stage's ENV block. UV_FROZEN and UV_FIND_LINKS are here because the
# wheelhouse and the frozen sync are what make an air-gapped install resolve at all.
OFFLINE_ENV = (
    "UV_CACHE_DIR=/opt/cache/uv",
    "UV_OFFLINE=1",
    "UV_FROZEN=1",
    "UV_FIND_LINKS=/opt/wheelhouse",
    "NPM_CONFIG_OFFLINE=true",
    "NPM_CONFIG_PREFER_OFFLINE=true",
    "GOPROXY=off",
)


def _instructions(dockerfile: str) -> str:
    """Drop comment lines, so a setting named in prose cannot satisfy an assertion."""
    return "\n".join(line for line in dockerfile.splitlines() if not line.lstrip().startswith("#"))


@pytest.fixture
def context(recipe: Path, tmp_path: Path) -> Path:
    return build(recipe, tmp_path / "ctx", tarball=False)


@pytest.fixture
def dockerfile(context: Path) -> str:
    """Read the assembled Dockerfile with comment lines dropped."""
    return _instructions((context / "Dockerfile").read_text(encoding="utf-8"))


def test_the_image_is_built_from_the_offline_stage(dockerfile: str) -> None:
    """`docker build` with no `--target` builds the last stage, so an appended one becomes the
    image. Stage references are resolved by `docker buildx build --check` in CI.
    """
    stages = _STAGE_DEF.findall(dockerfile)

    assert stages[-1] == "offline", f"the image is built from {stages[-1]}, not offline"


def test_context_carries_the_entrypoints_datarobot_connects_to(
    context: Path, dockerfile: str
) -> None:
    assert (context / "kernel" / "start_server_custom_model.sh").is_file()
    # DataRobot builds each deployed model FROM this image and runs this exact path.
    assert "COPY kernel/start_server_custom_model.sh /opt/code/start_server.sh" in dockerfile
    # The port the notebook kernel gateway is reached on; a codespace connects to nothing else.
    assert "EXPOSE 8888" in dockerfile


def test_every_copy_source_exists_in_the_context(context: Path) -> None:
    """A COPY naming a source the build never laid out fails only at `docker build` time,
    which nothing in CI runs. Derived from the Dockerfile, so an asset added later is covered.
    """
    dockerfile = (context / "Dockerfile").read_text(encoding="utf-8")
    sources = {
        source
        for flags, arguments in _COPY.findall(dockerfile)
        if "--from=" not in flags
        for source in arguments.split()[:-1]
        if "$" not in source
    }

    assert sources, "no COPY sources found"
    assert [source for source in sorted(sources) if not (context / source).exists()] == []


def test_license_headers_never_reach_the_generated_dockerfile(context: Path) -> None:
    """Fragment headers are Jinja comments, stripped at render time. A plain `#` header would
    still satisfy license-eye while shipping 14 lines of boilerplate in every Dockerfile.
    """
    assert "Apache License" not in (context / "Dockerfile").read_text(encoding="utf-8")


def test_context_offline_stage_is_offline_and_not_root(dockerfile: str) -> None:
    """The builder stages end as root on purpose, so `.hadolint.yaml` ignores DL3002; only the
    stage the image is built from matters.
    """
    offline_stage = dockerfile.split("AS offline", 1)[1]

    for setting in OFFLINE_ENV:
        assert setting in offline_stage, f"{setting} is not set in the offline stage"

    users = re.findall(r"^USER\s+(\S+)\s*$", offline_stage, re.MULTILINE)
    assert users, "the offline stage sets no USER"
    assert users[-1] != "root"


def test_only_manifest_bearing_components_are_laid_out(context: Path) -> None:
    # Keyed on the include name, not the directory basename: the cache stage COPYs this path.
    assert (context / "components" / "agent_app" / "pyproject.toml").is_file()
    assert (context / "components" / "agent_app" / "uv.lock").is_file()
    assert (context / "components" / "frontend" / "package.json").is_file()
    assert (context / "components" / "frontend" / "package-lock.json").is_file()
    # `docs` has no manifest, and `common` is an internal include, so neither is a component.
    assert not (context / "components" / "docs").exists()
    assert not (context / "components" / "common").exists()


def test_component_cache_stages_chain_and_the_offline_stage_copies_from_the_last(
    dockerfile: str,
) -> None:
    """A broken chain drops earlier components' caches out of the image, which only shows up
    as a missing package at deploy time.
    """
    chain = re.findall(r"^FROM\s+(\S+)\s+AS\s+(cache-\S+)\s*$", dockerfile, re.MULTILINE | re.I)
    assert chain == [
        ("kernel", "cache-agent_app"),
        ("cache-agent_app", "cache-frontend"),
        ("cache-frontend", "cache-perms"),
    ]
    # Scoped to the offline stage: a legal `--from=` in an earlier fragment is not this test's
    # business, and scanning the whole file would blame the offline stage for it.
    refs = set(_STAGE_REF.findall(dockerfile.split("AS offline", 1)[1]))
    component_stages = [stage for _, stage in chain if stage != "cache-perms"]
    assert "cache-perms" in refs
    assert refs <= {"cache-perms", component_stages[-1]}, (
        f"the offline stage copies from {refs - {'cache-perms', component_stages[-1]}}, "
        "which is not the end of the cache chain"
    )


def test_recipe_versions_file_overrides_the_built_in_defaults(context: Path) -> None:
    versions = (context / "dockerfile.d" / "02-versions.fragment").read_text(encoding="utf-8")

    # Neither value is a built-in default, so both prove the recipe's own file was read.
    assert "ARG UV_VERSION=0.10.3" in versions
    assert "ARG TASK_VERSION=3.45.4" in versions


def test_rebuild_replaces_the_target_rather_than_merging_into_it(
    recipe: Path, tmp_path: Path
) -> None:
    context = build(recipe, tmp_path / "ctx", tarball=False)
    stale = context / "dockerfile.d" / "50-stale.fragment"
    stale.write_text("FROM kernel AS stale\n", encoding="utf-8")

    build(recipe, tmp_path / "ctx", tarball=False)

    assert not stale.exists(), "a stale fragment survived a rebuild and would be assembled in"


# Parametrised rather than looped: a regression here deletes the target, so each case needs its
# own recipe copy. `.` covers an unset shell variable too, since Path("") is Path(".").
@pytest.mark.parametrize(
    "target",
    [".", "..", "agent", "Taskfile.yml"],
    ids=["dot", "parent", "component", "file"],
)
def test_build_refuses_a_target_that_already_holds_something_else(
    recipe: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    monkeypatch.chdir(recipe)

    with pytest.raises(ValueError, match="was not generated by this tool"):
        build(recipe, Path(target))

    assert (recipe / "Taskfile.yml").is_file(), "the recipe was deleted"
    assert (recipe / "agent" / "pyproject.toml").is_file(), "a component was deleted"


def test_tarball_holds_the_whole_context_and_nothing_outside_it(context: Path) -> None:
    archive = create_tarball(context)

    on_disk = {str(path.relative_to(context)) for path in context.rglob("*") if path.is_file()}
    with tarfile.open(archive) as tar:
        names = {m.name.removeprefix("./") for m in tar.getmembers() if m.isfile()}

    assert names == on_disk
    assert archive.parent == context.parent, "the archive must not sit inside the context"


def test_build_refuses_a_component_whose_lockfile_is_missing(recipe: Path, tmp_path: Path) -> None:
    (recipe / "agent" / "uv.lock").unlink()

    with pytest.raises(ValidationError) as error_info:
        build(recipe, tmp_path / "ctx", tarball=False)

    message = str(error_info.value)
    # Names the component, but points at the directory a contributor has to cd into.
    assert "component 'agent_app' has pyproject.toml but uv.lock is missing" in message
    assert "cd agent && uv lock" in message, "the error has to say how to fix it"
    assert not (tmp_path / "ctx").exists(), "a rejected recipe must not leave a partial context"


def test_build_runs_a_component_environment_hook_and_assembles_its_fragment(
    recipe: Path, tmp_path: Path, stub_task: Callable[[str], None]
) -> None:
    """Bare instructions appended to $DOCKERFILE_FRAGMENT extend the preceding cache stage, so
    this asserts the fragment is reachable from the image rather than merely present.
    """
    hook_dir = recipe / "custom"
    hook_dir.mkdir()
    (hook_dir / "Taskfile.yml").write_text(
        "version: '3'\ntasks:\n  environment:\n    cmds:\n      - true\n", encoding="utf-8"
    )
    taskfile = recipe / "Taskfile.yml"
    taskfile.write_text(
        taskfile.read_text(encoding="utf-8")
        + "  custom:\n    taskfile: ./custom/Taskfile.yml\n    dir: ./custom\n",
        encoding="utf-8",
    )

    stub_task('printf "RUN echo hooked\\n" >> "$DOCKERFILE_FRAGMENT"')

    context = build(recipe, tmp_path / "ctx", tarball=False)

    dockerfile = _instructions((context / "Dockerfile").read_text(encoding="utf-8"))
    assert "RUN echo hooked" in dockerfile

    # The stage the instructions landed in has to be the one the caches are copied out of,
    # or whatever the hook warmed is discarded.
    hook_stage = _STAGE_DEF.findall(dockerfile.split("RUN echo hooked")[0])[-1]
    perms = re.search(r"^FROM\s+(\S+)\s+AS\s+cache-perms", dockerfile, re.MULTILINE | re.I)
    assert perms is not None
    assert hook_stage == perms.group(1), (
        f"the hook's instructions landed in {hook_stage}, but the caches are copied out of "
        f"{perms.group(1)}"
    )
