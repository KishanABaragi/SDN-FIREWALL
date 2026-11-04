# Troubleshooting

## Before restarting

- Stop the running application with `Ctrl+C` in the terminal that launched `./RUN_APP.sh`.
- Do not run `mn -c` while Ryu is running. Mininet's cleanup command may terminate `ryu-manager`.
- The launcher checks ports 6001, 6003, 6653 and 8000, then runs Mininet cleanup before it starts Ryu.
- If the launcher says a port is already in use, identify and stop the old project instance first; do not repeatedly launch another copy.

## Startup order

The expected order is:

1. Ryu starts and opens its control interface on 6001 and OpenFlow listener on 6653.
2. Mininet creates `s1` and six hosts, then waits for OVS to report `is_connected=true`.
3. The application server on h3:5000 and logger on h4:6000 start.
4. FastAPI starts on 127.0.0.1:8000 and verifies all four components.

If startup fails, inspect the last lines of `logs/ryu.out`, `logs/mininet.out`, `logs/app_server.out`, `logs/logger_server.out` and `logs/dashboard_backend.out`.

## Common issues

### Ryu is missing

The launcher expects Ryu in the known pyenv Python 3.9.18 environment or available as `ryu-manager` on PATH. Confirm:

```bash
PYENV_VERSION=3.9.18 pyenv exec ryu-manager --version
```

### Mininet is missing for system Python

Confirm:

```bash
/usr/bin/python3 -c 'import mininet; print("Mininet OK")'
```

### OpenFlow switch does not connect

Check:

```bash
sudo ss -ltnp | grep 6653
sudo ovs-vsctl show
sudo ovs-vsctl list Controller
```

Ryu must be listening on 6653 and the OVS Controller row for `tcp:127.0.0.1:6653` must show `is_connected: true`. Do not run `mn -c` after Ryu starts.

### Dashboard API does not load

Check:

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/status
```

The dashboard is served by FastAPI from the same origin. A browser hard refresh (`Ctrl+Shift+R`) can clear stale static assets after replacing files.

### A test fails or is inconclusive

Open the test result's technical evidence and inspect the corresponding service logs. A failed or inconclusive result should not be presented as a pass. Test 5 intentionally waits for the actual controller timer; allow around 40 seconds and do not manually unblock during its verification window.

### Firewall test leaves a host blocked

Open Firewall controls, select the affected client, and choose Unblock. Confirm that a corresponding UNBLOCK event appears in the Event timeline.
