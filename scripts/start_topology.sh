#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
sudo mn -c
# Use system Python for Mininet imports; Ryu can run separately under pyenv Python 3.9.
exec sudo /usr/bin/python3 "$ROOT/src/topology.py"
