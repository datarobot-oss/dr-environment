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

echo "Persisting container environment variables for sshd..."
{
    echo "#!/bin/bash"
    echo "# This file is auto-populated with kernel env vars on container creation"
    echo "# to ensure that they are exposed in ssh sessions"
    echo "# Ref: https://github.com/jenkinsci/docker-ssh-agent/issues/33#issuecomment-597367846"
    echo "set -a"

    # set -a ensures that all modified/added shell variables are exported
    # ignore PWD/HOME/SHLVL/_ because these are specific to the current user and session
    # ignore TERM because it is set by asyncssh
    # ignore LD_PRELOAD for various security risks
    # ignore PS1 because it is set in setup-shell.sh
    env | grep -E -v "^(PWD=|HOME=|TERM=|SHLVL=|LD_PRELOAD=|PS1=|_=|KUBERNETES_)" | while read -r line; do
      NAME=$(echo "$line" | cut -d'=' -f1)
      VALUE=$(echo "$line" | cut -d'=' -f2-)
      ESCAPED=${VALUE//\'/\'\\\'\'}
      echo "$NAME='$ESCAPED'"
    done
    echo "set +a"
    # setup the working directory for terminal sessions
    echo "cd $WORKING_DIR"
} > /etc/profile.d/notebooks-load-env.sh && chmod 600 /etc/profile.d/notebooks-load-env.sh || {
    echo "Failed to write /etc/profile.d/notebooks-load-env.sh (check file ownership)" >&2
    return 1
}
