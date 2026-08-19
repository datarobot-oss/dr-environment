#!/bin/bash
# Re-export dependency cache paths for login shells (also set in Dockerfile ENV).
export UV_CACHE_DIR="${UV_CACHE_DIR:-/opt/cache/uv}"
export NPM_CONFIG_CACHE="${NPM_CONFIG_CACHE:-/opt/cache/npm}"
export NPM_CONFIG_PREFER_OFFLINE="${NPM_CONFIG_PREFER_OFFLINE:-true}"
export GOMODCACHE="${GOMODCACHE:-/opt/cache/go/pkg/mod}"
export GOCACHE="${GOCACHE:-/opt/cache/go/build}"

if [ "${NOTEBOOKS_AIR_GAP:-}" = "1" ]; then
  export UV_OFFLINE=1
  # Keep pypi.org (the index the baked uv cache was warmed against) queryable as an
  # extra index even if the platform's own env replaced UV_INDEX_URL with a private
  # mirror — uv keys cached registry metadata by index URL, so otherwise offline
  # `uvx`/`uv` calls only see the mirror's uncached index and fail.
  export UV_EXTRA_INDEX_URL="${UV_EXTRA_INDEX_URL:-https://pypi.org/simple}"
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
