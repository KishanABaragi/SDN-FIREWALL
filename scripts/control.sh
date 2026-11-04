#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${CONTROL_HOST:-127.0.0.1}"
PORT="${CONTROL_PORT:-6001}"
if [[ $# -lt 2 ]]; then
  echo "Usage: $0 BLOCK <MAC> [seconds] | UNBLOCK <MAC>" >&2
  exit 2
fi
action="${1^^}"
mac="${2,,}"
if [[ "$action" == "BLOCK" ]]; then
  seconds="${3:-30}"
  payload="BLOCK $mac $seconds"
elif [[ "$action" == "UNBLOCK" ]]; then
  payload="UNBLOCK $mac"
else
  echo "Action must be BLOCK or UNBLOCK" >&2; exit 2
fi
python3 - "$HOST" "$PORT" "$payload" <<'PY'
import socket,sys
host,port,payload=sys.argv[1],int(sys.argv[2]),sys.argv[3]
try:
    with socket.create_connection((host,port),timeout=4) as s:
        s.settimeout(4)
        s.sendall((payload+'\n').encode())
        print(s.recv(4096).decode(errors='replace').strip())
except OSError as e:
    print(f"Could not reach controller control socket at {host}:{port}: {e}",file=sys.stderr)
    print("Start Ryu first and confirm it reports 'Control interface listening'.",file=sys.stderr)
    sys.exit(1)
PY
