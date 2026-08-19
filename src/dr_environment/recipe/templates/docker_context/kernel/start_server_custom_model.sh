#!/bin/sh
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
#
# Adapted from datarobot/datarobot-user-models
# (public_dropin_environments/python311_genai_agents/start_server_custom_model.sh),
# relicensed Apache-2.0 for this repository. Modified: air-gap cache handling added,
# DRUM path removed, worker resolution changed.

# =============================================================================
# Startup script for Custom Model or MCP Server environments
# Determines which service to run based on directory contents
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Configure UV package manager
export UV_PROJECT="${CODE_DIR:-/opt/code}"
export UV_PROJECT_ENVIRONMENT="${VENV_DIR:-/opt/venv}"
export UV_COMPILE_BYTECODE=0  # Disable compilation
# Air-gapped images set UV_OFFLINE=1 and bake the dependency wheels into UV_CACHE_DIR;
# keep the cache enabled there so `uv sync` installs from it. When online, disable the
# cache so installs are reproducible and fetched fresh from the network.
if [ "${UV_OFFLINE:-0}" != "1" ]; then
    export UV_NO_CACHE=1
fi
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

# Create venv in code dir.
uv venv "${UV_PROJECT_ENVIRONMENT}"
# shellcheck disable=SC1091
. "${UV_PROJECT_ENVIRONMENT}/bin/activate"

# Sync dependencies using UV
# --active: Install into the active venv instead of creating a new one
# --frozen: Skip dependency resolution, use exact versions from lock file
# Note: Compilation disabled since kernel venv is already compiled
# Does not fail on errors to avoid blocking the startup of the server
uv sync --frozen --active --no-progress --color never || true

# Optional: Dump environment variables for debugging
if [ "${ENABLE_CUSTOM_MODEL_RUNTIME_ENV_DUMP}" = "1" ]; then
    echo "Environment variables:"
    env
fi

# -----------------------------------------------------------------------------
# Option 1: dragent Server
# Requires: workflow.yaml
# -----------------------------------------------------------------------------
if [ -f "$SCRIPT_DIR/workflow.yaml" ]; then
	# When running in a DR deployment, all paths should be mounted below ${URL_PREFIX}/
	ROOT_PATH_ARG=""
	if [ -n "${URL_PREFIX:-}" ]; then
		ROOT_PATH_ARG="--root_path ${URL_PREFIX}"
	fi

	# Get the number of workers from the runtime parameter (defaults to 1)
	CUSTOM_MODEL_WORKERS=$(python -c "from datarobot.core import getenv; print(int(getenv('CUSTOM_MODEL_WORKERS', '1')))")

	echo "Executing command: nat dragent serve --config_file $SCRIPT_DIR/workflow.yaml --port 8080 --use_gunicorn true --workers $CUSTOM_MODEL_WORKERS $ROOT_PATH_ARG"
	echo
	exec nat dragent serve --config_file $SCRIPT_DIR/workflow.yaml --host 0.0.0.0 --port 8080 --use_gunicorn true --workers $CUSTOM_MODEL_WORKERS $ROOT_PATH_ARG
fi

# -----------------------------------------------------------------------------
# Option 2: MCP Server
# Requires: app/ directory in the same location
# -----------------------------------------------------------------------------
if [ -d "$SCRIPT_DIR/app" ]; then
    echo "Starting Custom Model environment with MCP server"

    # Set Python path to script directory for module imports
    export PYTHONPATH="$SCRIPT_DIR"

    # Start the MCP server
    exec python -m app.main
fi

# -----------------------------------------------------------------------------
# Error: No valid entry point found
# -----------------------------------------------------------------------------
echo "Error: No valid entry point found in $SCRIPT_DIR"
echo "This script requires one of the following:"
echo "  - workflow.yaml file for dragent-based Agents"
echo "  - app/ directory for MCP Server applications"
exit 1
