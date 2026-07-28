#!/bin/bash
# Tool paths for login and SSH sessions. sshd resets PATH to a minimal Wolfi default.
export PATH="/etc/system/kernel/.venv/bin:/home/notebooks/.local/bin:/home/notebooks/.opencode/bin:${PATH}"
