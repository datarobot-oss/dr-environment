<p align="center">
  <a href="https://github.com/datarobot-oss/dr-environment">
    <img src="docs/img/datarobot_logo.avif" width="600px" alt="DataRobot Logo"/>
  </a>
</p>
<h3 align="center">DataRobot Execution Environment Builder</h3>

<p align="center">
  <a href="https://www.datarobot.com/">Homepage</a>
  ·
  <a href="https://docs.datarobot.com/en/docs/workbench/nxt-registry/nxt-custom-envs.html">Documentation</a>
  ·
  <a href="https://docs.datarobot.com/en/docs/get-started/troubleshooting/general-help.html">Support</a>
</p>

<p align="center">
  <a href="/LICENSE">
    <img src="https://img.shields.io/github/license/datarobot-oss/dr-environment" alt="License">
  </a>
</p>

Build a DataRobot execution environment that installs its dependencies with **no network access**.

`dr-environment` is a plugin for the [`dr` CLI](https://github.com/datarobot-oss/cli). Point it at a
DataRobot application directory and it writes a `docker_context/` you can build into a custom
execution environment image. Every Python, npm, and Go dependency is baked into the image as a
pre-warmed cache, so `uv sync`, `npm ci`, and `go mod download` all resolve offline at runtime.

> [!IMPORTANT]
> **Experimental.** This is a pre-1.0 tool under active development, published for air-gapped and
> network-restricted users. Interfaces may change without notice, and it is not covered by DataRobot
> support. For help, see [DataRobot support](https://docs.datarobot.com/en/docs/get-started/troubleshooting/general-help.html).

## How this relates to DataRobot custom environments

DataRobot already supports custom execution environments natively: in **Registry → Environments** you
can add an environment by building from a source archive, uploading a prebuilt image, or pulling from
an image URI. **That is the supported path, and you should use it.**

This tool does not replace it. It solves one problem the native "build from source archive" path
cannot: in an air-gapped or egress-restricted install, dependency resolution needs network access that
is not available at build time. `dr-environment` produces an image with every dependency already
cached, which you then hand to the native flow as a prebuilt image.

## Prerequisites

- [Docker](https://docs.docker.com/get-started/get-docker/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- The [`dr` CLI](https://github.com/datarobot-oss/cli)
- A DataRobot application directory, for example
  [datarobot-agent-application](https://github.com/datarobot-community/datarobot-agent-application)

## Install

This plugin installs from source; it is not yet in the `dr` plugin registry.

```bash
git clone https://github.com/datarobot-oss/dr-environment
cd dr-environment
uv tool install .
dr plugin list   # should now list `environment`
```

## Build an execution environment

**1. Generate the Docker context** from your application directory:

```bash
git clone https://github.com/datarobot-community/datarobot-agent-application
dr environment recipe --recipe-path datarobot-agent-application
```

This writes `docker_context/` and `docker_context.tar.gz` into the current directory. Pass
`--no-tarball` to skip the archive.

**2. Build the image** for `linux/amd64`, which DataRobot execution environments require:

```bash
cd docker_context
docker build --platform linux/amd64 -t exec-env .
```

On Apple Silicon you must pass `--platform linux/amd64`. An arm64 image fails at runtime with
`exec format error`.

**3. Export it to a tarball:**

```bash
docker image save exec-env -o image.tar
```

**4. Upload it to DataRobot.** In **Registry → Environments**, add a new environment, choose
**Upload a prebuilt image**, and select `image.tar`:

![Adding a prebuilt execution environment in the DataRobot Registry](docs/exec-env.png)

## What it produces

```
docker_context/
├── Dockerfile                 # assembled from dockerfile.d/*
├── dockerfile.d/              # one fragment per build stage
├── kernel/requirements.txt    # kernel-only deps (no root pyproject.toml)
├── components/<name>/         # copied manifests, one directory per component
├── setup-caches.sh
└── ...                        # runtime entrypoint scripts
```

The image runs Python 3.11, matching the `[DataRobot] Python 3.11 GenAI Agents` environment, and boots
Jupyter Kernel Gateway as the `notebooks` user.

## Lockfile policy

The build **fails** if a component has:

| Manifest | Required lockfile | Fix |
|---|---|---|
| `pyproject.toml` | `uv.lock` | `uv lock` |
| `package.json` | `package-lock.json` | `npm install` |
| `go.mod` | `go.sum` | `go mod tidy` |

Stale lockfiles fail too, detected via `uv lock --check`, `npm ci --dry-run`, and `go mod verify`. This
is deliberate: an offline image can only contain what a lockfile pinned.

## Offline behavior

The generated Dockerfile sets tool-native cache paths and strict offline flags:

| Variable | Value |
|---|---|
| `UV_CACHE_DIR` | `/opt/cache/uv` |
| `NPM_CONFIG_CACHE` | `/opt/cache/npm` |
| `GOMODCACHE` / `GOCACHE` | `/opt/cache/go` |
| `UV_OFFLINE` | `1` |
| `NPM_CONFIG_OFFLINE` | `true` |
| `GOPROXY` | `off` |

Each component gets its own cache stage running `uv sync --frozen --no-install-project` against its
own lockfile, so a runtime `uv sync --offline` resolves the exact platform-specific wheels it pinned.
Setting `NOTEBOOKS_AIR_GAP=1` applies the same overrides to login shells.

## Component hooks

If a component's `Taskfile.yml` defines an `environment` task, `dr environment recipe` runs it instead
of the default manifest copy, with:

| Variable | Purpose |
|---|---|
| `DOCKER_CONTEXT` | Output docker context path |
| `COMPONENT_DIR` | Source component directory |
| `COMPONENT_NAME` | Component name |
| `DOCKERFILE_FRAGMENT` | Path to append the cache-stage fragment to |
| `COMPONENT_DEST` | `components/<name>/` in the docker context |

The hook is responsible for copying its files and appending its own Dockerfile fragment.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Development setup and the architecture notes are in
[AGENTS.md](AGENTS.md).

```bash
uv sync --extra dev
uv run pytest
```

## License

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
