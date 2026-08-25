# Plugin Testing Guide

> Contributor documentation: this describes verifying changes **to** this repo.

## Installation

```bash
uv pip install -e .
dr-environment --dr-plugin-manifest
```

Expected manifest:

```json
{
  "name": "environment",
  "version": "0.1.0",
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

```bash
test -f docker_context/Dockerfile
test -f docker_context/kernel/requirements.txt
test ! -f docker_context/pyproject.toml
ls docker_context/components/
ls docker_context/dockerfile.d/
```

## Lockfile validation

Remove `uv.lock` from a component and run `recipe` — expect:

```
ERROR: component 'agent' has pyproject.toml but uv.lock is missing
  Fix: cd agent && uv lock
```

## Air-gap env vars

Inspect assembled Dockerfile final stage for cache and offline env vars:

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

```yaml
tasks:
  environment:
    cmds:
      - cp pyproject.toml uv.lock "$COMPONENT_DEST/"
      - |
        cat >> "$DOCKERFILE_FRAGMENT" <<'EOF'
        FROM cache-example AS cache-custom
        ENV UV_CACHE_DIR=/opt/cache/uv
        RUN echo custom stage
        EOF
```

Run `dr-environment recipe` and verify the fragment appears in `dockerfile.d/`.

## DataRobot CLI integration

After `uv tool install .`:

```bash
dr plugin list   # should include environment
dr environment recipe --recipe-path .
```
