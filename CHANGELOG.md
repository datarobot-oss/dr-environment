# Changelog

## Unreleased

### Fixed

- Pre-create the Agent Assist plugin venv at build time so Agent Assist launches in the offline image; it otherwise fails building the venv on first launch.
- Pin uv to the system CPython (`UV_PYTHON_PREFERENCE=system`) and pre-warm `uvx copier` into the baked offline cache so `dr start` (which runs `uvx copier recopy`) resolves copier offline. The Agent Assist step installs a managed CPython 3.11 that uv would otherwise prefer at runtime, making offline `uvx copier` resolve against an interpreter with no cached wheels and fail.

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
