#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if command -v pyenv >/dev/null 2>&1 && pyenv versions --bare 2>/dev/null | grep -qx '3.9.18' \
   && PYENV_VERSION=3.9.18 pyenv exec ryu-manager --help >/dev/null 2>&1; then
  exec env PYENV_VERSION=3.9.18 pyenv exec ryu-manager --ofp-tcp-listen-port 6653 src/security_controller.py
fi
command -v ryu-manager >/dev/null 2>&1 || { echo "ryu-manager not found in pyenv 3.9.18 or PATH" >&2; exit 127; }
exec ryu-manager --ofp-tcp-listen-port 6653 src/security_controller.py
