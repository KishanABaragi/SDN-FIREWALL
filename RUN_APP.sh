#!/usr/bin/env bash
# The only launcher users need to execute for the SDN Firewall application.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

banner() { printf '\n==================================================\n%s\n==================================================\n' "$1"; }
fail() { echo "[ERROR] $1" >&2; exit 1; }

banner "SDN FIREWALL — ONE-COMMAND STARTUP"

for cmd in sudo gcc python3 curl ss mn ovs-vsctl ovs-ofctl; do
  command -v "$cmd" >/dev/null 2>&1 || fail "Required command '$cmd' is missing. Install it before running this launcher."
done

# Ryu is intentionally kept in the project's existing pyenv Python 3.9.18
# environment when available; Mininet uses Ubuntu's system Python.
if command -v pyenv >/dev/null 2>&1 && pyenv versions --bare 2>/dev/null | grep -qx '3.9.18' \
   && PYENV_VERSION=3.9.18 pyenv exec ryu-manager --help >/dev/null 2>&1; then
  echo "[OK] Ryu found in pyenv Python 3.9.18."
elif command -v ryu-manager >/dev/null 2>&1 && ryu-manager --help >/dev/null 2>&1; then
  echo "[OK] Ryu found in PATH."
else
  fail "Ryu was not found. Activate/install the project's Ryu environment (the known working setup uses pyenv Python 3.9.18)."
fi

/usr/bin/python3 -c 'import mininet' >/dev/null 2>&1 || fail "Mininet is not installed for /usr/bin/python3. Install Mininet and Open vSwitch first."

# sudo must be authenticated before the privileged Mininet manager is detached.
banner "SUDO AUTHENTICATION"
sudo -v || fail "sudo authentication failed."
sudo -n true || fail "sudo credentials are not available to the launcher."

# Refuse to clean the Mininet environment if one of this project's service
# ports is already occupied. The cleanup must happen before Ryu is launched.
for port in 6001 6003 6653 8000; do
  if sudo ss -ltnH "sport = :$port" 2>/dev/null | grep -q LISTEN; then
    fail "Port $port is already in use. Stop the existing project instance before restarting."
  fi
done
banner "CLEANING STALE MININET STATE BEFORE RYU STARTS"
sudo mn -c

banner "BUILDING PROJECT COMPONENTS"
bash "$ROOT/build.sh"

banner "PREPARING DASHBOARD PYTHON ENVIRONMENT"
VENV="$ROOT/gui/backend/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV" || fail "Could not create the dashboard virtual environment. Install python3-venv."
fi
if ! "$VENV/bin/python" -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
  "$VENV/bin/python" -m pip install --disable-pip-version-check -r "$ROOT/gui/backend/requirements.txt" || fail "Dashboard dependencies could not be installed. Check internet access and pip output."
fi

mkdir -p "$ROOT/logs/runtime_logger"
banner "STARTING ALL SERVICES"
exec python3 "$ROOT/service_supervisor.py"
