<p align="center">
  <a href="https://github.com/datarobot-community/dr-environment">
    <img src="docs/img/datarobot_logo.avif" width="600px" alt="DataRobot Logo"/>
  </a>
</p>
<h3 align="center">DataRobot Execution Environment Builder</h3>

<p align="center">
  <a href="https://www.datarobot.com/">Homepage</a>
  ·
  <a href="https://docs.datarobot.com/en/docs/workbench/nxt-registry/nxt-environment-workshop/nxt-add-custom-env.html">Documentation</a>
  ·
  <a href="https://docs.datarobot.com/en/docs/get-started/troubleshooting/general-help.html">Support</a>
</p>

<p align="center">
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="License: Apache 2.0">
  </a>
</p>

Build Codespace-ready execution environment Docker contexts for DataRobot App Framework recipes. Uses a **customer-buildable Wolfi base** with Python 3.11 and pre-warmed shared **uv**, **npm**, and **Go** dependency caches.

> [!NOTE]
> Early development (`0.1.0`). The generated Dockerfile and the CLI flags may change between
> releases. Released under DataRobot's open-source program; it does not carry an official support
> SLA. See [SECURITY.md](SECURITY.md).

## How this relates to DataRobot custom environments

The built-in environments in DataRobot Registry are the supported default, and the stock
`[DataRobot] Python 3.11 GenAI Agents` environment is the right choice for most projects. This tool
covers the air-gapped case: it produces an environment with every dependency cache baked in, so the
image runs with no network access. Its output is uploaded through the same custom execution
environment flow as any other image.

## Prerequisites

- [Docker](https://docs.docker.com/get-started/get-docker/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- The `dr` CLI, which hosts this plugin:

```bash
curl https://cli.datarobot.com/install | sh
# or: brew install datarobot-oss/taps/dr-cli
```

Lockfile validation runs each ecosystem's own tool, so a recipe may also need
[Node.js](https://nodejs.org/en/download) for a `package.json`, [Go](https://go.dev/dl/) for a
`go.mod`, or [Task](https://taskfile.dev/installation/) for an `environment` hook.

## Install

```bash
git clone https://github.com/datarobot-community/dr-environment.git
cd dr-environment
uv tool install -e .
```

## Make an execution environment

1. Generate the Docker context from your App Framework recipe:

```bash
dr environment recipe --recipe-path datarobot-agent-application
```

This writes `docker_context/` in the current working directory (and `docker_context.tar.gz` unless you pass `--no-tarball`).

2. Change into the generated context:

```bash
cd docker_context
```

3. Build the image for **linux/amd64** (required for DataRobot notebook kernels):

```bash
docker build --platform linux/amd64 -t exec-env .
```

On Apple Silicon, always pass `--platform linux/amd64`. An arm64 image fails at runtime with `exec format error` on `start_server.sh`.

4. Export the image to a tarball:

```bash
docker image save exec-env -o image.tar
```

5. Upload `image.tar` as a custom execution environment in DataRobot:

![Upload execution environment in DataRobot](docs/exec-env.png)

## Usage reference

```bash
dr environment recipe --recipe-path /path/to/datarobot-agent-application
```

Defaults:

- Output: `docker_context/` in the current working directory (override with `--target`)
- Archive: `docker_context.tar.gz` in the current working directory
- Versions: `.datarobot/cli/versions.yaml`

### Options

```bash
dr environment recipe --recipe-path . --no-tarball
```

## What it produces

```
docker_context/
├── Dockerfile                 # assembled from dockerfile.d/*
├── dockerfile.d/              # one fragment per build stage
├── build-deps/                # build-time manifests
├── kernel/                    # kernel deps, entrypoints, Jupyter assets
│   ├── requirements.txt       # kernel-only deps
│   ├── setup-caches.sh        # offline cache paths for login shells
│   ├── start_server_*.sh      # Codespaces and deployed-model entrypoints
│   └── agent/, extensions/    # kernel assets
└── components/<name>/         # per-component manifests
```

## Lockfile policy

Build **fails** if a component has:

- `pyproject.toml` without `uv.lock` (fix: `uv lock`)
- `package.json` without `package-lock.json` (fix: `npm install`)
- `go.mod` without `go.sum` (fix: `go mod tidy`)
- Stale lockfiles (`uv lock --check`, `npm ci --dry-run`, or `go mod verify` failure)

## Runtime cache behavior

The Dockerfile sets tool-native env vars:

- `UV_CACHE_DIR=/opt/cache/uv`
- `NPM_CONFIG_CACHE=/opt/cache/npm`
- `NPM_CONFIG_PREFER_OFFLINE=true`
- `GOMODCACHE` / `GOCACHE`

Per-component cache stages run `uv sync --frozen --no-install-project` against each `uv.lock` so runtime `uv sync --offline` can resolve lockfile wheels (including platform-specific builds like `litellm`).

The Dockerfile always sets strict offline env vars (`UV_OFFLINE=1`, `NPM_CONFIG_OFFLINE=true`, `GOPROXY=off`) in addition to shared cache paths. `NOTEBOOKS_AIR_GAP=1` in `setup-caches.sh` applies the same overrides for login shells.

This is deliberate and always-on, not a toggle for the platform to opt out of. Without `UV_OFFLINE=1`, a cache miss makes uv fall through to whatever `UV_INDEX_URL`/mirror is configured in the environment — in an air-gapped install that host can be unreachable, or have no access to a certain library. So instead of a fast, clear "not found in the cache" error, the install hangs until the request times out or fails. Keeping this image strictly offline trades "install anything, sometimes slowly or not at all" for "install only what's baked, fail fast and clearly otherwise." A platform that needs to install extra, non-baked packages from its own reachable mirror should do so outside this image (e.g. in a derived image or a separate step), not by unsetting these vars here.

## Component hooks

If a component Taskfile defines an `environment` task, `dr environment recipe` runs it with:

| Variable | Purpose |
|----------|---------|
| `DOCKER_CONTEXT` | Output docker context path |
| `COMPONENT_DIR` | Source component directory |
| `COMPONENT_NAME` | Component name |
| `DOCKERFILE_FRAGMENT` | Path to append cache stage fragment |
| `COMPONENT_DEST` | `components/<name>/` in docker context |

## Development

```bash
uv pip install -e ".[dev]"
pytest
dr-environment --dr-plugin-manifest
```

See [PLUGIN_TESTING.md](PLUGIN_TESTING.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

That grant covers this repository's own code. It does not extend to the components the generated
image fetches at build time, which keep their own terms, including Wolfi apk packages under GPL-2.0
and GPL-3.0, and the DataRobot Python SDK under the DataRobot Tool and Utility Agreement.
