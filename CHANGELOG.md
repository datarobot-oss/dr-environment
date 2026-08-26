# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 0.1.3
- Bump kernel `ecs-logging` from 2.2.0 to 2.3.0.
- Bump kernel `gunicorn` from 26.0.0 to 26.1.0.
- Bump kernel `ipykernel` from 6.28.0 to 7.3.0.
- Bump kernel `jupyter-client` from 8.6.3 to 8.9.1.

## 0.1.2
- Bump `ruff` from 0.16.3 to 0.16.4.

## 0.1.1
- Bump CI GitHub Actions: `actions/checkout` to 7.0.1, `actions/setup-python` to 7.0.0, `astral-sh/setup-uv` to 10.0.1, `actions/cache` to 6.1.0, `actions/upload-artifact` to 7.0.1, `actions/download-artifact` to 8.0.1.

## 0.1.0
- Publish to PyPI on merge to `main`. Install with `uv tool install dr-environment`.
- Require a version bump and a changelog entry on any pull request that changes what ships, bot authors included (previously exempt).
- Announce pull requests awaiting review in Slack.
- Adopt the shared `datarobot-oss/github-actions` pull-request automation, pinned at `0.0.24`: every pull request must record what changed in this file (waivable with the `skip-changelog` label, and skipped for bot authors so weekly Dependabot bumps do not each need one), approved pull requests are labelled `00 - Reviewed`, and a Jira ticket named in the title or branch is linked as a comment.
- Prepare for the first public release: correct the third-party notices, pin the base image and build-time dependencies, and harden the build.
- Host deployed agent and MCP custom models. DataRobot builds each deployed model FROM this image and runs `/opt/code/start_server.sh`; provide that entrypoint (a dispatcher: `workflow.yaml` → agent via `nat dragent serve`, `app/` → MCP server via `python -m app.main`), matching the stock GenAI Agents execution environment. Without it the model image build failed at `chmod /opt/code/start_server.sh`. For air-gapped deployments, models install their dependencies from the baked cache: uv's cache stays enabled under `UV_OFFLINE=1` (instead of the default reproducible-but-online `UV_NO_CACHE`), `/opt/venv` is pre-created writable, and the baked uv cache is made writable by the model's runtime user (uid 1000).
- Bundle the GitHub CLI (`gh`) via Wolfi apk for offline use. A stopgap: not version-managed through `versions.yaml` like the other tools, so drop it when unused.
- Add a security policy, Dependabot version updates, and a `pip-audit` CI job.
- Bake a find-links wheelhouse at `/opt/wheelhouse` (the exact published wheels/sdists of every Python component) and point `UV_FIND_LINKS` at it. DataRobot builds the FastAPI custom application FROM this image with `uv pip install --system --no-cache`, and `--no-cache` makes uv ignore the baked uv cache — so in an air-gapped install the build had no wheels to read and failed (e.g. `ag-ui-protocol was not found in the cache`). `--no-cache` does not disable find-links, and `pip download` fetches the exact published artifacts so their hashes match the deploy-time requirements. No `--only-binary=:all:` here: components pull in arbitrary packages we don't control, and legitimate pure-Python packages regularly stop publishing wheels without being any less safe to build offline (e.g. `rouge-score` is sdist-only since `0.0.7` but pure Python, needing only the `setuptools` this repo already bakes in) — rejecting all sdists would fail builds over packages that build fine.
- Build the execution environment on Python 3.11 (was 3.12) to match the stock `[DataRobot] Python 3.11 GenAI Agents` environment. On 3.12, deployed DRAgent agents crash-loop on boot: uvicorn aliases its `asyncio_run` to `asyncio.run`, which NAT patches via `nest_asyncio` and cannot patch a uvloop event loop (`Can't patch loop of type uvloop.Loop`). On 3.11 uvicorn uses its own `asyncio.Runner`-based path that bypasses the patch, so agents start under multi-worker gunicorn. All component lockfiles already allow 3.11 (`requires-python >=3.11`) and resolve unchanged.
- Pre-create the Agent Assist plugin venv at build time so Agent Assist launches in the offline image; it otherwise fails building the venv on first launch.
- Pin uv to the system CPython (`UV_PYTHON_PREFERENCE=system`) and pre-warm `uvx copier` into the baked offline cache so `dr start` (which runs `uvx copier recopy`) resolves copier offline. The Agent Assist step installs a managed CPython 3.11 that uv would otherwise prefer at runtime, making offline `uvx copier` resolve against an interpreter with no cached wheels and fail.
- Source `setup-caches.sh` from `setup-venv.sh` via the script's own directory instead of `${WORKDIR}`. `WORKDIR` is a build-time ARG and is empty at runtime, so the baked Pulumi provider plugins were never seeded into the platform's `PULUMI_HOME` (mounted persistent storage), and `pulumi up` tried to download them — failing offline.
- Download copier's dependency closure into the `/opt/wheelhouse` find-links directory at build time, with `pip download --only-binary=:all:` so a future copier release pulling in a transitive dep with no published wheel fails this build step loudly instead of baking an sdist that would need a compiler toolchain to build offline at the customer's runtime. uv keys cached registry metadata by index URL, so an offline install that points `UV_INDEX_URL` at its own private mirror couldn't see anything cached under `pypi.org` — including the baked `uvx copier` warm-up — and `uvx copier` (run by `dr start`) failed with "packages must be downloaded from a registry". Find-links reads wheels straight off disk with no index/URL/network involved, so it resolves regardless of what `UV_INDEX_URL` is set to.
- Bake `UV_FROZEN=1` into the offline image env and `setup-caches.sh`. Plain `uv sync` (no `--frozen`) checks the lock against the currently configured uv index before installing; an air-gapped install that points `UV_INDEX_URL` at its own mirror fails that check (wrong index recorded in the lock, not just unreachable) and re-resolves from scratch, which fails offline — e.g. a component's `uv sync --extra dev` task failed with "ecs-logging was not found in the cache" purely because of the mirror override, even though its lockfile hadn't changed. `UV_FROZEN=1` makes every `uv sync` in the image skip that check and install straight from `uv.lock`, without having to add `--frozen` to every component Taskfile individually.
- Download the PEP 517 build backends (`hatchling`, `editables`, `setuptools`, `pip`) into the `/opt/wheelhouse` find-links directory at build time (also with `pip download --only-binary=:all:`), alongside the existing uv-cache warm-up. `uv sync` on a local/editable component (e.g. `core`) builds it via its `build-system.requires`, which uv resolves against whatever index is currently configured regardless of `UV_FROZEN`/`--frozen` — so an install pointing `UV_INDEX_URL` at its own mirror couldn't see `hatchling` cached under `pypi.org` and failed with "hatchling was not found in the cache".
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
