#!/bin/bash
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
# Re-export dependency cache paths for login shells (also set in Dockerfile ENV).
export UV_CACHE_DIR="${UV_CACHE_DIR:-/opt/cache/uv}"
export NPM_CONFIG_CACHE="${NPM_CONFIG_CACHE:-/opt/cache/npm}"
export NPM_CONFIG_PREFER_OFFLINE="${NPM_CONFIG_PREFER_OFFLINE:-true}"
export GOMODCACHE="${GOMODCACHE:-/opt/cache/go/pkg/mod}"
export GOCACHE="${GOCACHE:-/opt/cache/go/build}"
# Makes every `uv sync` (including ones run by component Taskfiles) install straight
# from uv.lock instead of first checking the lock against the currently configured uv
# index — a check that fails (wrong index, not just unreachable) whenever UV_INDEX_URL
# points at a private mirror instead of whatever index the lock was resolved against.
export UV_FROZEN="${UV_FROZEN:-1}"

if [ "${NOTEBOOKS_AIR_GAP:-}" = "1" ]; then
  export UV_OFFLINE=1
  export NPM_CONFIG_OFFLINE=true
  export GOPROXY=off
fi

# Provider plugins are baked into $HOME/.pulumi/plugins at image build time, but the platform
# points PULUMI_HOME at mounted persistent storage, which starts out empty on that volume.
# Copy them in (symlinks aren't picked up by `pulumi plugin ls`) so pulumi finds them without
# re-downloading at runtime.
BAKED_PULUMI_PLUGINS="${HOME}/.pulumi/plugins"
RUNTIME_PULUMI_PLUGINS="${PULUMI_HOME:-${HOME}/.pulumi}/plugins"
if [ -d "$BAKED_PULUMI_PLUGINS" ] && [ "$RUNTIME_PULUMI_PLUGINS" != "$BAKED_PULUMI_PLUGINS" ]; then
  mkdir -p "$RUNTIME_PULUMI_PLUGINS"
  shopt -s nullglob
  for plugin in "$BAKED_PULUMI_PLUGINS"/*/; do
    name="$(basename "$plugin")"
    target_dir="${RUNTIME_PULUMI_PLUGINS}/${name}"
    [ -e "$target_dir" ] || cp -a "$plugin" "$target_dir"
  done
  shopt -u nullglob
fi
