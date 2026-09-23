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
"""Bake the agent component's template into the image and cache every framework it offers.

`task start` recopies the agent with any framework, so offline the template must come from the
image and every framework's wheels from the baked uv cache.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import click
import yaml

from dr_environment.recipe.models import Component, ComponentStrategy
from dr_environment.recipe.validate import TOOL_INSTALL_HINTS

ANSWERS_DIR = ".datarobot/answers"
FRAMEWORK_QUESTION = "agent_template_framework"
# True hides FRAMEWORK_QUESTION on templates before 11.11.85 and copier then drops `--data` for
# it, so every render answers false; nat stays one of the choices either way.
LOW_CODE_QUESTION = "use_low_code_interface"
# Under the docker context, and the mount point in the image.
TEMPLATES_DIR = "component-templates"
TEMPLATES_MOUNT = "/opt/component-templates"


@dataclass(frozen=True)
class BakedTemplate:
    """A template clone under TEMPLATES_DIR, and the origin URL git redirects to it."""

    src_path: str
    name: str

    @property
    def url(self) -> str:
        return f"file://{TEMPLATES_MOUNT}/{self.name}"


def find_agent_answers(recipe_path: Path, component: Component) -> Path | None:
    """Return the copier answers file of an af-component-agent render, else None."""
    pyproject = component.source_dir / "pyproject.toml"
    if not pyproject.is_file():
        return None
    marker = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("tool", {})
    if marker.get("af-component", {}).get("type") != "agent":
        return None
    for answers in sorted((recipe_path / ANSWERS_DIR).glob("*.yml")):
        data = yaml.safe_load(answers.read_text(encoding="utf-8")) or {}
        if data.get("agent_app_name") == component.source_dir.name and "_src_path" in data:
            return answers
    click.echo(
        f"WARNING: agent component '{component.name}' has no copier answers file under "
        f"{ANSWERS_DIR}; its template and frameworks are not baked",
        err=True,
    )
    return None


def expand_agent_variants(
    recipe_path: Path, components: list[Component], work_dir: Path
) -> tuple[list[Component], list[BakedTemplate]]:
    """Return one extra component per distinct framework lock, and the templates to bake.

    Renders live under `work_dir`, which must outlive the layout step that copies them.
    """
    extra: list[Component] = []
    templates: dict[str, BakedTemplate] = {}
    order = max((component.fragment_order for component in components), default=9) + 1
    for component in components:
        if component.strategy != ComponentStrategy.DEFAULT:
            continue
        answers_file = find_agent_answers(recipe_path, component)
        if answers_file is None:
            continue
        answers = yaml.safe_load(answers_file.read_text(encoding="utf-8"))
        template = _clone_template(str(answers["_src_path"]), templates, work_dir / TEMPLATES_DIR)
        # The recipe's own framework and nat (same lock as base) dedupe away. Only uv.lock is
        # compared; the template ships no npm or Go manifests.
        seen = {_digest(component.source_dir / "uv.lock")}
        cached: list[str] = []
        renders = _render_frameworks(
            answers,
            answers_file,
            work_dir / TEMPLATES_DIR / template.name,
            work_dir / component.name,
        )
        for framework, render in renders:
            digest = _digest(render / "uv.lock")
            if digest in seen:
                continue
            seen.add(digest)
            extra.append(
                Component(
                    name=f"{component.name}-{framework}", source_dir=render, fragment_order=order
                )
            )
            order += 1
            cached.append(framework)
        click.echo(
            f"{component.name}: baked {template.src_path} at {answers['_commit']}; "
            f"cached {len(cached)} extra framework(s): {', '.join(cached) or 'none'}"
        )
    return extra, list(templates.values())


def _clone_template(
    src_path: str, templates: dict[str, BakedTemplate], templates_dir: Path
) -> BakedTemplate:
    # Repeatable component: two agents share one origin, and a bare clone holds every tag.
    if src_path in templates:
        return templates[src_path]
    name = src_path.rstrip("/").rsplit("/", 1)[-1]
    template = BakedTemplate(src_path, name if name.endswith(".git") else f"{name}.git")
    clash = next((t for t in templates.values() if t.name == template.name), None)
    if clash is not None:
        raise ValueError(
            f"two agent templates would both be baked as {template.name}: "
            f"{clash.src_path} and {src_path}"
        )
    clone = templates_dir / template.name
    clone.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", "--quiet", "--bare", src_path, str(clone)], what=f"cloning {src_path}")
    templates[src_path] = template
    return template


def _render_frameworks(
    answers: dict, answers_file: Path, clone: Path, renders_dir: Path
) -> Iterator[tuple[str, Path]]:
    """Render the template once per framework choice; yield (framework, agent directory)."""
    src_path, commit = str(answers["_src_path"]), str(answers["_commit"])
    copier_yml = yaml.safe_load(
        _run(
            ["git", "-C", str(clone), "show", f"{commit}:copier.yml"],
            capture_output=True,
            what=f"reading copier.yml of {src_path} at {commit}",
        ).stdout
    )
    choices = copier_yml[FRAMEWORK_QUESTION]["choices"]
    # Copier also allows a list of pairs or a template string; neither iterates as frameworks.
    if not isinstance(choices, dict):
        raise ValueError(
            f"{FRAMEWORK_QUESTION} choices in copier.yml of {src_path} at {commit} must be a "
            f"mapping of label to value, got {type(choices).__name__}"
        )
    # Forward every persisted answer but the framework; copier's `_` keys are not answers.
    forwarded = {
        key: value
        for key, value in answers.items()
        if not key.startswith("_") and key not in (FRAMEWORK_QUESTION, LOW_CODE_QUESTION)
    }
    forwarded[LOW_CODE_QUESTION] = False
    for framework in choices.values():
        dest = renders_dir / framework
        # The template reads the base and llm answers from the sibling files.
        shutil.copytree(answers_file.parent, dest / ANSWERS_DIR)
        command = ["uvx", "copier", "copy", "--quiet", "--defaults", "--vcs-ref", commit]
        for key, value in (*forwarded.items(), (FRAMEWORK_QUESTION, framework)):
            command += ["--data", f"{key}={value}"]
        what = f"rendering {framework} from {src_path} at {commit}"
        _run([*command, str(clone), str(dest)], what=what)
        # A hidden question drops --data; a render that fell back to the default would dedupe
        # away and ship an image without that framework's wheels.
        rendered = yaml.safe_load((dest / ANSWERS_DIR / answers_file.name).read_text("utf-8"))
        if rendered.get(FRAMEWORK_QUESTION) != framework:
            raise RuntimeError(
                f"ERROR: {what} answered {FRAMEWORK_QUESTION}="
                f"{rendered.get(FRAMEWORK_QUESTION)!r}; the template ignored the requested value"
            )
        render = dest / str(answers["agent_app_name"])
        if not (render / "uv.lock").is_file():
            raise RuntimeError(f"ERROR: {what} produced no uv.lock in {render}")
        yield framework, render


def _digest(lockfile: Path) -> str:
    # Callers guarantee the file: the recipe's lock passed validation, a render's is checked.
    return sha256(lockfile.read_bytes()).hexdigest()


def _run(
    command: list[str], *, what: str, capture_output: bool = False
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, text=True, capture_output=capture_output)
    except FileNotFoundError as exc:
        tool = command[0]
        raise FileNotFoundError(
            f"ERROR: '{tool}' is required for {what} but is not installed\n"
            f"  Install: {TOOL_INSTALL_HINTS[tool]}"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = f"\n{exc.stderr.strip()}" if exc.stderr else ""
        raise RuntimeError(f"ERROR: {what} failed (exit {exc.returncode}){detail}") from exc
