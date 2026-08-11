# Changelog

## Unreleased

### Added

- Host deployed agent and MCP custom models. DataRobot builds each deployed model FROM this image and runs `/opt/code/start_server.sh`; provide that entrypoint (a dispatcher: `workflow.yaml` → agent via `nat dragent serve`, `app/` → MCP server via `python -m app.main`), matching the stock GenAI Agents execution environment. Without it the model image build failed at `chmod /opt/code/start_server.sh`. For air-gapped deployments, models install their dependencies from the baked cache: uv's cache stays enabled under `UV_OFFLINE=1` (instead of the default reproducible-but-online `UV_NO_CACHE`), `/opt/venv` is pre-created writable, and the baked uv cache is made writable by the model's runtime user (uid 1000).
- Bundle the GitHub CLI (`gh`) via Wolfi apk. Temporary workaround — remove once no longer needed.

### Fixed

- Build the execution environment on Python 3.11 (was 3.12) to match the stock `[DataRobot] Python 3.11 GenAI Agents` environment. On 3.12, deployed dragent agents crash-loop on boot: uvicorn aliases its `asyncio_run` to `asyncio.run`, which NAT patches via `nest_asyncio` and cannot patch a uvloop event loop (`Can't patch loop of type uvloop.Loop`). On 3.11 uvicorn uses its own `asyncio.Runner`-based path that bypasses the patch, so agents start under multi-worker gunicorn. All component lockfiles already allow 3.11 (`requires-python >=3.11`) and resolve unchanged.
- Pre-create the Agent Assist plugin venv at build time so Agent Assist launches in the offline image; it otherwise fails building the venv on first launch.
- Pin uv to the system CPython (`UV_PYTHON_PREFERENCE=system`) and pre-warm `uvx copier` into the baked offline cache so `dr start` (which runs `uvx copier recopy`) resolves copier offline. The Agent Assist step installs a managed CPython 3.11 that uv would otherwise prefer at runtime, making offline `uvx copier` resolve against an interpreter with no cached wheels and fail.
- Source `setup-caches.sh` from `setup-venv.sh` via the script's own directory instead of `${WORKDIR}`. `WORKDIR` is a build-time ARG and is empty at runtime, so the baked Pulumi provider plugins were never seeded into the platform's `PULUMI_HOME` (mounted persistent storage), and `pulumi up` tried to download them — failing offline.

## Version 0.1.0 (2026-07-23)

### Added

- `dr-environment plan` — inspect recipe components, lockfile status, and strategies
- `dr-environment build` — assemble execution environment docker context with:
  - Per-component manifest copy under `components/<name>/`
  - Per-component Dockerfile cache stages (`uv pip install` cache warm, `npm ci`, `go mod download`)
  - Kernel-only `kernel/requirements.txt` (no root `pyproject.toml`)
  - Tool-native cache env vars in final image (`UV_CACHE_DIR`, `NPM_CONFIG_*`, `GOMODCACHE`)
  - `dockerfile.d/*.fragment` assembly into `Dockerfile`
  - Optional `docker_context.tar.gz`
- Lockfile validation (missing/stale) with remediation messages
- Component `environment` Taskfile hook support
- Codespaces-only kernel stage (no custom model `start_server` wiring)
- Strict offline Dockerfile env vars always baked in (`UV_OFFLINE`, `NPM_CONFIG_OFFLINE`, `GOPROXY=off`)
- Tests for discovery, validation, and Dockerfile assembly
