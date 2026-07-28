#!/bin/bash
# Re-export dependency cache paths for login shells (also set in Dockerfile ENV).
export UV_CACHE_DIR="${UV_CACHE_DIR:-/opt/cache/uv}"
export NPM_CONFIG_CACHE="${NPM_CONFIG_CACHE:-/opt/cache/npm}"
export NPM_CONFIG_PREFER_OFFLINE="${NPM_CONFIG_PREFER_OFFLINE:-true}"
export GOMODCACHE="${GOMODCACHE:-/opt/cache/go/pkg/mod}"
export GOCACHE="${GOCACHE:-/opt/cache/go/build}"

if [ "${NOTEBOOKS_AIR_GAP:-}" = "1" ]; then
  export UV_OFFLINE=1
  export NPM_CONFIG_OFFLINE=true
  export GOPROXY=off
fi
