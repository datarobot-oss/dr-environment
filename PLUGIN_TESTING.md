# Plugin Testing Guide

> Contributor documentation: this describes verifying changes **to** this repo.

Most of what follows is now automated. `uv run pytest` builds a context from
`tests/fixtures/recipe` and asserts the layout, the stage order, the offline environment and
the hook contract; CI additionally lints the generated Dockerfile with hadolint and resolves
its stage graph with `docker buildx build --check`. Run the steps below when changing the
templates, or to check something the suite does not reach: a real `docker build`, an image
that runs with no network, and a recipe with npm or Go components. The fixture recipe is
locked with `uv` and `npm` once per session; without either on PATH those tests skip, naming
the missing tool.

## Installation

```bash
uv pip install -e .
dr-environment --dr-plugin-manifest
```

Expected manifest, where `version` is whatever `pyproject.toml` declares:

```json
{
  "name": "environment",
  "version": "X.Y.Z",
  "description": "Build execution environment Docker contexts with offline dependency caches",
  "authentication": false
}
```

## Recipe against a local checkout

```bash
cd /path/to/datarobot-agent-application
uv run dr-environment recipe --recipe-path .
```

## Build output

Asserted by `tests/recipe/test_build.py`; check by hand only against a real recipe.

```bash
test -f docker_context/Dockerfile
test -f docker_context/kernel/requirements.txt
test ! -f docker_context/pyproject.toml
ls docker_context/components/
ls docker_context/dockerfile.d/
```

## Image build

Not covered by CI. The base image is `wolfi-base:latest` and the build fetches from seven
external hosts, so it is neither reproducible nor hermetic.

```bash
cd docker_context
docker build --platform linux/amd64 -t exec-env .
docker run --rm --network none exec-env sh -c 'uv sync --offline && uvx copier --version'
```

## Lockfile validation

Remove `uv.lock` from a component and run `recipe` — expect:

```
ERROR: component 'agent' has pyproject.toml but uv.lock is missing
  Fix: cd agent && uv lock
```

## Air-gap env vars

Asserted by `tests/recipe/test_build.py`. The final stage sets:

```
UV_CACHE_DIR=/opt/cache/uv
NPM_CONFIG_PREFER_OFFLINE=true
UV_OFFLINE=1
NPM_CONFIG_OFFLINE=true
GOPROXY=off
```

Verify `kernel/start_server_custom_model.sh` is copied to `/opt/code/start_server.sh`. DataRobot builds each deployed model FROM this image and runs that path; Codespaces sessions use `start_server_codespaces.sh` instead.

## Component hook

Add to a component `Taskfile.yml`:

The task receives five variables: `DOCKER_CONTEXT`, `COMPONENT_DIR`, `COMPONENT_NAME`,
`DOCKERFILE_FRAGMENT` (pre-created, append to it) and `COMPONENT_DEST` (pre-created, copy into
it). `tests/recipe/test_hooks.py` pins all five against a stubbed `task`; this checks the same
contract against the real one.

```yaml
tasks:
  environment:
    cmds:
      - cp pyproject.toml uv.lock "$COMPONENT_DEST/"
      - |
        cat >> "$DOCKERFILE_FRAGMENT" <<'EOF'
        RUN echo custom step
        EOF
```

Run `dr-environment recipe` and verify the fragment appears in `dockerfile.d/`.

Append bare instructions, as above: they land in the preceding cache stage, which is part of the
chain the offline stage copies from. A fragment that opens its own `FROM ... AS ...` stage is
assembled but never referenced, so anything it warms is discarded.

## DataRobot CLI integration

After `uv tool install .`:

```bash
dr plugin list   # should include environment
dr environment recipe --recipe-path .
```
