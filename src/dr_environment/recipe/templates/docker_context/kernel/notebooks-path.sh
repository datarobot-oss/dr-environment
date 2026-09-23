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
# Tool paths for login and SSH sessions (sshd resets PATH). The venv must end up first and once:
# the recipe's app start script strips one leading venv entry to reach the system python.
tools="/etc/system/kernel/.venv/bin:/home/notebooks/.local/bin:/home/notebooks/.opencode/bin"
rest=""
_old_ifs="$IFS"; IFS=:
for dir in $PATH; do
  case ":${tools}:" in
    *":${dir}:"*) ;;
    *) rest="${rest:+${rest}:}${dir}" ;;
  esac
done
IFS="$_old_ifs"; unset _old_ifs
export PATH="${tools}${rest:+:${rest}}"
unset tools rest dir
