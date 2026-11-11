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

PS1='[\[\033[38;5;172m\]\u\[$(tput sgr0)\]@kernel \[$(tput sgr0)\]\[\033[38;5;39m\]\w\[$(tput sgr0)\]]\$ \[$(tput sgr0)\]'

# shellcheck disable=SC1091
source /etc/system/kernel/setup-venv.sh
