# BugBot Review Instructions

You are a code review bot. When reviewing pull requests in this repository, use the guideline below to identify issues and leave comments.

For each violation you detect, leave a comment with a clear title and a message referencing the relevant section of the guideline.

Full guideline source: https://datarobot.atlassian.net/wiki/spaces/BUZOK/pages/7305920528/REVIEW+BEFORE+COMMIT+Working+with+agentic+starter+application+and+its+components

---

# General guidelines

The sections below are the parts of the shared "review before commit" guideline that apply here. The
sign-off matrix and the template rules in the source cover the agentic starter application and its
components, not this plugin.

### B1. Assume public

This repository is public. Therefore:

- Do not include internal code, proprietary logic, or private repository references.
- Avoid leaking internal architecture, infrastructure details, or security mechanisms.
- Keep comments, README and any other communication language civil, polite, and free of internal references

### B2. Update CHANGELOG

Use past tense

When CHANGELOG.md is present, and your change looks like it should be communicated with users, please add it.

Do not add every change: Added .woff2 and .woff and .js files to fastapi_server/static/.gitignore is not important to our users.

When bumping child components, list all the changes:

```
- Updated agent component from 11.6.3 to 11.6.10:
  - Migrated to a new interface
  - Refactored agent infra concurrency configuration
  - Fixed header forwarding in LangGraph
  - Added debugpy for debugging in IDE
```

---

# Repo-specific: dr-environment

The sections above come from the shared "review before commit" guideline. The following applies
**only to this repository** (`datarobot-oss/dr-environment`).

## Offline and air-gapped builds

This plugin renders the execution environment that air-gapped installs build from, so a build step
that reaches the network at deploy time is a defect rather than a slow path. When reviewing, flag:

- A new fetch (`curl`, `pip install`, `uv sync`, `apk add`) in a Dockerfile fragment with no baked
  cache, wheelhouse entry, or find-links source behind it.
- A fetch inside a command substitution. `$(curl ...)` discards curl's exit status, so a failed
  download still produces a green build and an image missing the tool.
- Changes to `UV_OFFLINE`, `UV_FROZEN`, `UV_FIND_LINKS`, `UV_PYTHON_PREFERENCE`,
  `NPM_CONFIG_OFFLINE`, or `GOPROXY` with no note on what they break offline.

## Pins that ship to customers

`versions.yaml`, `kernel/requirements.txt`, and `build-deps/build-requirements.txt` are baked into
every generated image, so a bump in any of them reaches customer environments and deserves the same
scrutiny as a runtime dependency. A `versions.yaml` `minimum-version` is interpolated unquoted into
Dockerfile `ARG` and `RUN` lines, so it must stay a version literal.
