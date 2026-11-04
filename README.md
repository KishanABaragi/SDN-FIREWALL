# Dynamic Firewall with Security Event Logger

A local web dashboard for the six-host Mininet / Open vSwitch / Ryu firewall project. The dashboard brings service health, topology, host blocking, seven interactive validation tests, controller events and network measurements into one interface.

## Start and stop

Run the application from this directory:

```bash
./RUN_APP.sh
```

The launcher checks the required commands and Python environments, verifies that the project's service ports are not already occupied, cleans stale Mininet state **before Ryu starts**, builds the C programs, prepares the FastAPI environment, then starts Ryu → Mininet → the dashboard in sequence. Keep the terminal open. Press `Ctrl+C` in that terminal to stop the services.

Open `http://127.0.0.1:8000/` if the browser does not open automatically. The dashboard is intentionally bound to localhost; do not expose its control API to an untrusted network.

## Architecture

| Component | Location | Purpose |
|---|---|---|
| Ryu security controller | `src/security_controller.py` | OpenFlow 1.3 controller; control socket on `127.0.0.1:6001`; OpenFlow listener on `127.0.0.1:6653` |
| Mininet manager | `src/mininet_daemon.py` | Creates six hosts and switch `s1`; manager API on `127.0.0.1:6003` |
| Application server | h3 · `10.0.0.3:5000` | Receives client TCP messages and returns ACKs |
| Event logger | h4 · `10.0.0.4:6000` | Receives newline-delimited JSON security events |
| Dashboard API | `gui/backend/main.py` | FastAPI service on `127.0.0.1:8000` |
| Dashboard UI | `gui/frontend/` | Static HTML, CSS and JavaScript; no frontend build step |

Host addresses and MAC addresses are defined in `src/topology.py`:

| Host | IP | MAC | Role |
|---|---|---|---|
| h1 | 10.0.0.1 | 00:00:00:00:00:01 | Client / automatic-detection source |
| h2 | 10.0.0.2 | 00:00:00:00:00:02 | Client / firewall test target |
| h3 | 10.0.0.3 | 00:00:00:00:00:03 | Application server |
| h4 | 10.0.0.4 | 00:00:00:00:00:04 | Event logger |
| h5 | 10.0.0.5 | 00:00:00:00:00:05 | Client |
| h6 | 10.0.0.6 | 00:00:00:00:00:06 | Client |

## Dashboard guide

- **Overview:** live service checks, switch state and recent activity.
- **Network map:** controller / switch / host layout and host directory.
- **Firewall controls:** select a host and apply or remove a timed block. Avoid blocking h3 or h4 because they run the application and logger services.
- **Test centre:** run any of seven tests individually or run the full suite. Every result includes a status, plain-language summary, step-by-step checks and technical evidence where available.
- **Event timeline:** inspect records from `logs/controller_events.csv` and the network logger.
- **Performance:** view measurements collected by the live tests. Empty values mean no current-run measurement has been collected.
- **Quick guide:** in-dashboard operating notes.

## Seven tests

1. **TCP communication** — h1 sends four messages to h3 and the runner counts ACK replies.
2. **Traffic visibility** — creates TCP traffic and compares Open vSwitch packet counters before and after.
3. **Firewall block & recovery** — measures h1→h2 reachability, blocks h2, verifies loss, unblocks h2 and verifies recovery.
4. **Central event logger** — checks that a client session creates CONNECT and DISCONNECT records in the logger file.
5. **Automatic detection & timed recovery** — sends repeated SYN attempts from h1, checks for a controller CSV BLOCK record, waits for the controller's own timer and checks for an automatic UNBLOCK record and post-expiry connectivity. It does not manually unblock to manufacture a pass. This test takes approximately 40 seconds.
6. **Network performance** — collects live h1→h3 ping loss and average RTT.
7. **Concurrent clients** — runs h1 and h2 simultaneously and counts ACK replies.

A test is marked **PASS** only when its defined evidence is observed. **FAIL** means the test ran but an expected condition was not met. **INCONCLUSIVE** means the runner could not prove the behaviour. **ERROR** means execution failed. Review technical evidence before using a result in a report.

## Dependencies

The Ubuntu VM needs Mininet, Open vSwitch, GCC, Python 3, `python3-venv`, `sudo`, `ss`, and Ryu. The known working Ryu setup uses pyenv Python 3.9.18. The dashboard's FastAPI / Uvicorn dependencies are installed into `gui/backend/.venv` by `RUN_APP.sh` from `gui/backend/requirements.txt`.

Typical Ubuntu packages if missing:

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch gcc python3 python3-venv iproute2 curl
```

Install or activate Ryu in the existing pyenv 3.9.18 environment as configured for your VM. The launcher intentionally does not silently install or replace Ryu.

## Logs and evidence

- `logs/ryu.out`, `logs/mininet.out`, `logs/dashboard_backend.out` — service output.
- `logs/controller_events.csv` — controller BLOCK / UNBLOCK records.
- `logs/runtime_logger/security_events.log` — network logger records.
- `logs/app_server.out`, `logs/logger_server.out` — C service output.
- `evidence/` and `docs/` — retained project evidence and reference documents.

Historical evidence files are retained for reference and are not represented as newly generated test results.

## Safety and measurement notes

- The dashboard binds to `127.0.0.1`; keep it local because firewall actions change live switch rules.
- The timed block is enforced by Ryu. The UI only reports recovery after the controller event log shows an UNBLOCK record.
- The controller's `duration_ms` field measures rule-submission time, not end-to-end enforcement latency. Do not label it as end-to-end response time.
- The automatic-detection test uses the controller's configured repeated-SYN threshold and default timed block. Packet visibility depends on the live OpenFlow path, so validate it in the target VM.

## Troubleshooting

See `TROUBLESHOOTING.md`. Do not run `mn -c` after Ryu starts: Mininet cleanup can terminate `ryu-manager`. The launcher runs cleanup before starting Ryu; the Mininet manager itself does not perform startup cleanup.
