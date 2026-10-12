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

# Sets the max user processes (ulimit -u) via NOTEBOOKS_NPROC_LIMIT.
# Coerce to a positive integer; fall back to default if the env value is
# missing, non-numeric, or zero/negative (don't trust the value blindly: it is
# interpolated into a script that gets sourced from /etc/profile.d).
DEFAULT_NPROC_LIMIT=8192
if [ -z "${NOTEBOOKS_NPROC_LIMIT:-}" ]; then
    echo "NOTEBOOKS_NPROC_LIMIT not set, defaulting to ${DEFAULT_NPROC_LIMIT}." >&2
    nproc_limit=$DEFAULT_NPROC_LIMIT
elif ! [[ "$NOTEBOOKS_NPROC_LIMIT" =~ ^[1-9][0-9]*$ ]]; then
    echo "NOTEBOOKS_NPROC_LIMIT='${NOTEBOOKS_NPROC_LIMIT}' is not a positive integer, defaulting to ${DEFAULT_NPROC_LIMIT}." >&2
    nproc_limit=$DEFAULT_NPROC_LIMIT
else
    nproc_limit=$NOTEBOOKS_NPROC_LIMIT
fi

echo "Generating common bash profile..."
{
    echo "#!/bin/bash"
    echo "# Setting user process limits."
    echo "ulimit -Su ${nproc_limit}"
    echo "ulimit -Hu ${nproc_limit}"
} > /etc/profile.d/bash-profile-load.sh
