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
"""The `--fips` additions to the generated Dockerfile, run outside Docker where they can be."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from dr_environment.template.cache.stages import CacheStage
from dr_environment.template.render import (
    docker_context_root,
    render_base_fragment,
    render_offline_fragment,
)
from dr_environment.template.versions import _DEFAULTS

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "fips"
GUARD_DIR = docker_context_root() / "kernel" / "fips"


def _base_fragment(tmp_path: Path) -> str:
    render_base_fragment(tmp_path, dict(_DEFAULTS), fips_base_image="example/python-fips")
    return (tmp_path / "dockerfile.d" / "00-base.fragment").read_text(encoding="utf-8")


def _offline_fragment(tmp_path: Path, *, fips: bool) -> str:
    (tmp_path / "dockerfile.d").mkdir(parents=True, exist_ok=True)
    stages = [CacheStage("cache-agent", ("/opt/cache/uv", "/opt/wheelhouse"))]
    render_offline_fragment(tmp_path, cache_stages=stages, fips=fips)
    return (tmp_path / "dockerfile.d" / "99-offline.fragment").read_text(encoding="utf-8")


def _run_instruction(fragment: str, marker: str) -> str:
    """Return the shell command of the RUN instruction that contains *marker*."""
    for match in re.finditer(r"^RUN (.*?)(?<!\\)\n", fragment, re.MULTILINE | re.DOTALL):
        if marker in match.group(1):
            return match.group(1)
    raise AssertionError(f"no RUN instruction contains {marker!r}")


def _gnu_sed() -> bool:
    return shutil.which("sed") is not None and (
        subprocess.run(["sed", "--version"], capture_output=True, check=False).returncode == 0
    )


@pytest.mark.skipif(not _gnu_sed(), reason="the instruction uses GNU sed's `-i`")
def test_the_openssl_cnf_patch_drops_the_legacy_provider(tmp_path: Path) -> None:
    """Chainguard's legacy provider lets plain hashlib.md5() through; the patch must remove it
    and keep the default provider (hashlib needs it at import) and the FIPS defaults.
    """
    cnf = tmp_path / "openssl.cnf"
    shutil.copy(FIXTURES / "chainguard-openssl.cnf", cnf)
    command = _run_instruction(_base_fragment(tmp_path), "openssl.cnf")

    result = subprocess.run(
        ["bash", "-c", command.replace("/etc/ssl/openssl.cnf", str(cnf))],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    patched = cnf.read_text(encoding="utf-8")
    assert "legacy" not in patched
    assert "CHAINGUARD" not in patched
    assert "[default_sect]\nactivate = 1" in patched
    assert "default_properties = fips=yes" in patched


def test_the_fips_base_builds_crypto_from_source_and_turns_on_go_fips(tmp_path: Path) -> None:
    fragment = _base_fragment(tmp_path)

    assert 'UV_NO_BINARY_PACKAGE="cryptography grpcio"' in fragment
    assert 'PIP_NO_BINARY="cryptography,grpcio"' in fragment
    assert "GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=1" in fragment
    assert "GODEBUG=fips140=on" in fragment
    assert "COPY kernel/fips /etc/datarobot-fips/" in fragment


def test_the_fips_offline_stage_puts_the_guard_on_pythonpath_and_checks_linkage(
    tmp_path: Path,
) -> None:
    fips = _offline_fragment(tmp_path / "fips", fips=True)
    plain = _offline_fragment(tmp_path / "plain", fips=False)

    assert 'PYTHONPATH="/etc/datarobot-fips:' in fips
    assert "readelf -d" in _run_instruction(fips, "libssl")
    assert "datarobot-fips" not in plain
    assert "readelf" not in plain


@pytest.mark.parametrize(
    ("enforce", "expected_exit"),
    [(None, 0), ("false", 0), ("true", 78)],
)
def test_the_guard_halts_only_when_fips_is_enforced_without_fips_mode(
    enforce: str | None, expected_exit: int
) -> None:
    """Outside FIPS mode the guard stays silent unless DATAROBOT_FIPS_ENFORCE=true, which must
    stop the process with exit 78 and the FATAL line the platform greps for.
    """
    env = {k: v for k, v in os.environ.items() if k != "DATAROBOT_FIPS_ENFORCE"}
    env["PYTHONPATH"] = str(GUARD_DIR)
    if enforce is not None:
        env["DATAROBOT_FIPS_ENFORCE"] = enforce
    probe = "import _hashlib; print(bool(getattr(_hashlib, 'get_fips_mode', lambda: 0)()))"
    in_fips_mode = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False
    ).stdout
    if in_fips_mode == "True\n":
        pytest.skip("this interpreter's OpenSSL is in FIPS mode")

    result = subprocess.run(
        [sys.executable, "-c", "print('started')"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == expected_exit, result.stderr
    if expected_exit:
        assert "[datarobot-fips] FATAL" in result.stderr
        assert "started" not in result.stdout
    else:
        assert result.stdout == "started\n"
        assert result.stderr == ""
