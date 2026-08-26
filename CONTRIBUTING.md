# Contributing Guidelines

Guidelines for developing and contributing to this project.

## List of project maintainers

- [Anatolii Stehnii](https://github.com/tsdaemon)
- [Andrey Mukomolov](https://github.com/sir-Gollum)


## Opening new issues

- Before opening a new issue check if there are any existing FAQ entries (if one exists), issues or pull requests that match your case
- Open an issue, and make sure to label the issue accordingly - bug, improvement, feature request, etc...
- Be as specific and detailed as possible

## Did you find a bug?

- For a security vulnerability, do not open an issue; see [SECURITY.md](SECURITY.md)
- Ensure the bug was not already reported in the projects Issues section
- Open an issue as described above

## Changelog

All pull requests should include an entry in the [CHANGELOG.md](CHANGELOG.md) file.

This is enforced by the `Changelog` workflow, bots included. If a change has no consumer-visible
effect (a typo, a CI-only tweak), apply the `skip-changelog` label instead.

## Versioning

A merge to `main` releases the version `pyproject.toml` declares. A pull request that changes what
ships must bump `[project].version` and file its changelog entry under that version; without the
bump the merge goes green and publishes nothing. The `Version` workflow enforces this, waivable
with the `skip-version-bump` label. What ships: anything under `src/`, plus `pyproject.toml`,
`README.md`, `LICENSE`, `NOTICE`, `AUTHORS`.

## Responding to issues and pull requests

This project's maintainers will make every effort to respond to any
open issues as soon as possible.

If you don't get a response within seven days of creating your issue or
pull request, please send us an email at oss-community-management@datarobot.com
