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

# we don't want it output anything in the terminal session setup
VERBOSE_MODE=${1:-false}

# Resolve setup-caches.sh next to this script. WORKDIR is a build-time ARG and is
# not set at runtime, so sourcing via ${WORKDIR} silently skipped setup-caches.sh
# (and its Pulumi plugin seeding) in kernel and login shells.
KERNEL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
if [ -f "${KERNEL_DIR}/setup-caches.sh" ]; then
  source "${KERNEL_DIR}/setup-caches.sh"
fi

IS_CODESPACE=$([[ "${WORKING_DIR}" == *"/storage"* ]] && echo true || echo false)
IS_PYTHON_KERNEL=$([[ "${NOTEBOOKS_KERNEL}" == "python" ]] && echo true || echo false)

if [[ $IS_CODESPACE == true ]]; then
  export XDG_CACHE_HOME="${WORKING_DIR%/}/.cache"
  export XDG_CONFIG_HOME="${WORKING_DIR%/}/.config"
  export XDG_CONFIG_DIRS="${HOME}/.config"
  export COLORTERM=truecolor
fi

if [[ $IS_CODESPACE == true && $IS_PYTHON_KERNEL == true && -z "${NOTEBOOKS_NO_PERSISTENT_DEPENDENCIES}" ]]; then
  export POETRY_VIRTUALENVS_CREATE=false
  # Persistent HF artifact installation
  export HF_HOME="${WORKING_DIR%/}/.cache"
  export HF_HUB_CACHE="${WORKING_DIR%/}/.cache"
  export HF_DATASETS_CACHE="${WORKING_DIR%/}/.datasets"
  export TRANSFORMERS_CACHE="${WORKING_DIR%/}/.models"
  export SENTENCE_TRANSFORMERS_HOME="${WORKING_DIR%/}/.models"

  USR_VENV="${WORKING_DIR%/}/.venv"
  [[ $VERBOSE_MODE == true ]] && echo "Setting up a user venv ($USR_VENV)..."

  # we need to make sure both kernel & user venv's site-packages are in PYTHONPATH because:
  # - when the user venv is activated (e.g. terminal sessions), it ignores the kernel venv
  # - when Jupyter kernel is running (e.g. notebook cells) it uses the kernel venv ignoring the user venv

  # shellcheck disable=SC1091
  source "$VENV_PATH/bin/activate"
  KERNEL_PACKAGES=$(python -c "import site; print(site.getsitepackages()[0])")
  deactivate

  # If a user has previously created a session with a different python version we need to figure that out
  # If so we'll delete the existing venv to avoid errors and issues - for example when pip installing new packages
  if [ -d "$USR_VENV" ]; then
    [[ $VERBOSE_MODE == true ]] && echo "$USR_VENV does exist - will check python symlinks to see if they are broken..."
    readarray -d '' VENV_SYMLINKS < <(find "$USR_VENV" -type l -print0)
    python_symlinks_broken=false
    for i in "${VENV_SYMLINKS[@]}"; do
      if [[ "$i" == *"python"* ]]; then
        [[ $VERBOSE_MODE == true ]] && echo "Checking symlink (${i})."
        if [ ! -e "$i" ]; then
          [[ $VERBOSE_MODE == true ]] && echo "Symlink (${i}) broken..."
          python_symlinks_broken=true
          break
        fi
      fi
    done

    if [[ $python_symlinks_broken == true ]]; then
      [[ $VERBOSE_MODE == true ]] && echo "Python symlinks are broken - deleting existing virtual env..."
      rm -rf "${USR_VENV}"
    fi
  fi

  python3 -m venv "${USR_VENV}"
  # shellcheck disable=SC1091
  source "${USR_VENV}/bin/activate"
  USER_PACKAGES=$(python -c "import site; print(site.getsitepackages()[0])")

  export PYTHONPATH="$USER_PACKAGES:$KERNEL_PACKAGES:$PYTHONPATH"
else
  [[ $VERBOSE_MODE == true ]] && echo "Skipping user venv setup..."
  # App Framework exec envs set NOTEBOOKS_NO_PERSISTENT_DEPENDENCIES — components own their venvs;
  # do not auto-activate kernel venv in SSH (would steer dr/task installs to the wrong environment).
  if [[ -z "${NOTEBOOKS_NO_PERSISTENT_DEPENDENCIES}" ]]; then
    # shellcheck disable=SC1091
    source "$VENV_PATH/bin/activate"
  fi
fi
