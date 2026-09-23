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
"""Rendering every framework of the agent template, and baking the template itself."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from dr_environment.recipe.discover import discover_components
from dr_environment.recipe.models import Component, ComponentStrategy
from dr_environment.recipe.variants import (
    BakedTemplate,
    expand_agent_variants,
    find_agent_answers,
)


def test_a_component_without_the_agent_marker_has_no_answers(recipe: Path) -> None:
    component = Component(name="agent_app", source_dir=recipe / "agent")

    assert find_agent_answers(recipe, component) is None


def test_the_agent_component_is_paired_with_its_answers_file(agent_recipe: Path) -> None:
    component = Component(name="agent_app", source_dir=agent_recipe / "agent")

    answers = find_agent_answers(agent_recipe, component)

    assert answers == agent_recipe / ".datarobot" / "answers" / "agent-agent.yml"


def test_an_agent_without_answers_is_reported_not_skipped_silently(
    agent_recipe: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (agent_recipe / ".datarobot" / "answers" / "agent-agent.yml").unlink()
    component = Component(name="agent_app", source_dir=agent_recipe / "agent")

    assert find_agent_answers(agent_recipe, component) is None
    assert "agent_app" in capsys.readouterr().err


def test_a_recipe_without_an_agent_component_is_left_alone(recipe: Path, tmp_path: Path) -> None:
    components = discover_components(recipe)

    assert expand_agent_variants(recipe, components, tmp_path / "work") == ([], [])


def test_a_hook_component_is_left_alone(agent_recipe: Path, tmp_path: Path) -> None:
    components = discover_components(agent_recipe)
    for component in components:
        component.strategy = ComponentStrategy.HOOK

    assert expand_agent_variants(agent_recipe, components, tmp_path / "work") == ([], [])


def test_each_distinct_resolution_becomes_a_component_and_the_template_is_cloned(
    agent_recipe: Path,
    template_repo: Path,
    stub_uvx: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Base re-renders the recipe's lock and nat resolves like base; only crewai survives."""
    components = discover_components(agent_recipe)
    work = tmp_path / "work"

    extra, templates = expand_agent_variants(agent_recipe, components, work)

    assert [component.name for component in extra] == ["agent_app-crewai"]
    variant = extra[0]
    assert (variant.source_dir / "uv.lock").is_file()
    assert variant.fragment_order > max(component.fragment_order for component in components)

    assert templates == [BakedTemplate(src_path=str(template_repo), name="af-component-agent.git")]
    clone = work / "component-templates" / "af-component-agent.git"
    # A bare clone, at the recipe's pinned version: copier clones it with `-r <_commit>`.
    assert (clone / "HEAD").is_file() and not (clone / ".git").exists()
    subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "--verify", "-q", "1.0.0^{commit}"], check=True
    )

    calls = stub_uvx.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 3, "one render per framework listed in the template's copier.yml"
    for call in calls:
        # Forwarded answers: a render differs from the recipe in the framework alone.
        assert call.startswith("argv copier copy ")
        assert "--vcs-ref 1.0.0" in call
        assert "--data use_agent_memory=none" in call
        assert "--data agent_app_name=agent" in call
        # The recipe answered low-code; a hidden framework question would swallow --data.
        assert "--data use_low_code_interface=False" in call
        assert "use_low_code_interface=true" not in call
        assert f" {clone} " in call
    assert [call.split("agent_template_framework=")[1].split()[0] for call in calls] == [
        "base",
        "crewai",
        "nat",
    ]
    assert "agent_app: baked" in capsys.readouterr().out


def test_two_agents_from_one_template_share_a_clone(
    agent_recipe: Path, template_repo: Path, stub_uvx: Path, tmp_path: Path
) -> None:
    """A repeatable component must not re-clone into the same directory."""
    shutil.copytree(agent_recipe / "agent", agent_recipe / "agent2")
    answers = agent_recipe / ".datarobot" / "answers"
    (answers / "agent-agent2.yml").write_text(
        (answers / "agent-agent.yml")
        .read_text(encoding="utf-8")
        .replace("agent_app_name: agent\n", "agent_app_name: agent2\n"),
        encoding="utf-8",
    )
    taskfile = agent_recipe / "Taskfile.yml"
    spec = yaml.safe_load(taskfile.read_text(encoding="utf-8"))
    spec["includes"]["agent2"] = {"taskfile": "./agent2/Taskfile.yml", "dir": "./agent2"}
    taskfile.write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")

    extra, templates = expand_agent_variants(
        agent_recipe, discover_components(agent_recipe), tmp_path / "work"
    )

    assert len(templates) == 1
    assert sorted(component.name for component in extra) == ["agent2-crewai", "agent_app-crewai"]


def test_choices_that_are_not_a_mapping_are_rejected(
    agent_recipe: Path, template_repo: Path, stub_uvx: Path, tmp_path: Path
) -> None:
    """Copier also allows a list of pairs or a template string; neither may be iterated."""
    (template_repo / "copier.yml").write_text(
        "agent_template_framework:\n  type: str\n  choices:\n    - [Base, base]\n    - [CrewAI, crewai]\n",
        encoding="utf-8",
    )
    for args in (
        ("add", "copier.yml"),
        ("-c", "user.name=f", "-c", "user.email=f@e.com", "commit", "-q", "-m", "list"),
        ("tag", "-f", "1.0.0"),
    ):
        subprocess.run(["git", "-C", str(template_repo), *args], check=True, capture_output=True)

    with pytest.raises(ValueError, match="choices"):
        expand_agent_variants(agent_recipe, discover_components(agent_recipe), tmp_path / "work")


def test_a_render_that_ignored_the_requested_framework_is_rejected(
    agent_recipe: Path,
    template_repo: Path,
    stub_uvx: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hidden question drops --data; the render would dedupe away and ship a thin image."""
    monkeypatch.setenv("UVX_IGNORE_FRAMEWORK", "1")

    with pytest.raises(RuntimeError, match=r"rendering crewai .*agent_template_framework='base'"):
        expand_agent_variants(agent_recipe, discover_components(agent_recipe), tmp_path / "work")


def test_a_failed_render_names_the_framework_and_the_template(
    agent_recipe: Path,
    template_repo: Path,
    stub_uvx: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UVX_FAIL", "crewai")

    with pytest.raises(RuntimeError, match=r"rendering crewai .*1\.0\.0"):
        expand_agent_variants(agent_recipe, discover_components(agent_recipe), tmp_path / "work")
