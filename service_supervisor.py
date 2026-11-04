#!/usr/bin/env python3
"""Single-session supervisor for the SDN Firewall project.

RUN_APP.sh performs prerequisite checks/builds, then starts this supervisor.
The supervisor owns Ryu, the privileged Mininet manager and the dashboard.
"""
from __future__ import annotations
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)
SERVICES = {}
STOPPING = False


def port_open(port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def tail_log(name: str, lines: int = 35) -> None:
    path = LOGS / f"{name}.out"
    print(f"\n--- Last lines of {path.relative_to(ROOT)} ---", flush=True)
    if path.exists():
        content = path.read_text(errors="replace").splitlines()
        print("\n".join(content[-lines:]) or "(empty)", flush=True)
    else:
        print("(log not created)", flush=True)


def spawn(name: str, command: list[str]) -> subprocess.Popen:
    log = open(LOGS / f"{name}.out", "w", buffering=1)
    proc = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        # Keep sudo's Mininet child in the same login session (so the cached
        # sudo timestamp is valid), but give it its own process group so Ctrl+C
        # is handled by this supervisor and shutdown can signal the whole tree.
        start_new_session=(name != "mininet"),
        preexec_fn=(os.setpgrp if name == "mininet" else None),
    )
    SERVICES[name] = (proc, log)
    (LOGS / f"{name}.pid").write_text(str(proc.pid))
    print(f"[OK] Started {name} (PID {proc.pid})", flush=True)
    return proc


def wait_for_port(name: str, port: int, timeout: int = 40) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        proc = SERVICES[name][0]
        if proc.poll() is not None:
            tail_log(name)
            raise RuntimeError(f"{name} exited with code {proc.returncode}")
        if port_open(port):
            print(f"[OK] {name} is listening on 127.0.0.1:{port}", flush=True)
            return
        time.sleep(0.5)
    tail_log(name)
    raise RuntimeError(f"Timed out waiting for {name} on port {port}")


def manager_request(payload: dict, timeout: float = 4.0) -> dict:
    with socket.create_connection(("127.0.0.1", 6003), timeout=timeout) as conn:
        conn.settimeout(timeout)
        conn.sendall(json.dumps(payload).encode())
        chunks = []
        while True:
            part = conn.recv(8192)
            if not part:
                break
            chunks.append(part)
            # Manager replies are a single JSON object; it closes after sending.
        return json.loads(b"".join(chunks).decode())


def wait_for_switch(timeout: int = 45) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        if SERVICES["mininet"][0].poll() is not None:
            tail_log("mininet")
            raise RuntimeError("Mininet manager exited unexpectedly")
        try:
            last = manager_request({"action": "STATUS"}, timeout=3)
            if last.get("running") and last.get("switch_connected"):
                if last.get("app_server") and last.get("logger"):
                    print("[OK] Switch connected; application server and logger are running", flush=True)
                    return last
        except Exception:
            pass
        time.sleep(1)
    tail_log("mininet")
    tail_log("ryu")
    raise RuntimeError(f"Mininet did not confirm an OpenFlow connection and both services. Last status: {last}")


def shutdown(*_args) -> None:
    global STOPPING
    if STOPPING:
        return
    STOPPING = True
    print("\nStopping SDN Firewall services...", flush=True)

    # Ask the Mininet manager to stop its hosts and topology cleanly first.
    try:
        manager_request({"action": "STOP"}, timeout=3)
    except Exception as exc:
        print(f"[WARN] Manager graceful-stop request: {exc}", flush=True)

    # Give Mininet time to stop host processes and release OVS resources.
    if "mininet" in SERVICES:
        proc = SERVICES["mininet"][0]
        try:
            proc.wait(timeout=12)
        except subprocess.TimeoutExpired:
            print("[WARN] Mininet manager did not exit; terminating its process group", flush=True)
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    # Stop dashboard and Ryu after Mininet has disconnected.
    for name in ("dashboard_backend", "ryu"):
        if name not in SERVICES:
            continue
        proc = SERVICES[name][0]
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    for name, (proc, log) in SERVICES.items():
        try:
            if proc.poll() is None:
                proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        log.close()
        (LOGS / f"{name}.pid").unlink(missing_ok=True)

    # Mininet's own net.stop() normally removes its bridge. This is a final
    # cleanup only if sudo credentials are still cached.
    if "mininet" in SERVICES:
        subprocess.run(["sudo", "-n", "mn", "-c"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=15, check=False)
    print("[OK] Shutdown sequence finished.", flush=True)


def main() -> int:
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        # Refuse to silently attach to unrelated processes.
        for port in (6001, 6003, 6653, 8000):
            if port_open(port):
                raise RuntimeError(
                    f"Port {port} is already in use. Stop the old project instance or identify the other service first."
                )

        print("\n[1/4] Starting Ryu controller...", flush=True)
        spawn("ryu", ["bash", str(ROOT / "scripts" / "run_controller.sh")])
        wait_for_port("ryu", 6001, 45)
        wait_for_port("ryu", 6653, 45)

        print("\n[2/4] Starting six-host Mininet manager...", flush=True)
        spawn("mininet", ["sudo", "-n", "/usr/bin/python3", str(ROOT / "src" / "mininet_daemon.py")])
        wait_for_port("mininet", 6003, 75)
        wait_for_switch(45)

        print("\n[3/4] Starting dashboard backend...", flush=True)
        python = ROOT / "gui" / "backend" / ".venv" / "bin" / "python"
        spawn("dashboard_backend", [str(python), "-m", "uvicorn", "main:app",
                                     "--app-dir", str(ROOT / "gui" / "backend"),
                                     "--host", "127.0.0.1", "--port", "8000"])
        wait_for_port("dashboard_backend", 8000, 40)

        print("\n[4/4] Verifying dashboard service status...", flush=True)
        deadline = time.monotonic() + 15
        status = {}
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/api/status", timeout=3) as response:
                    status = json.loads(response.read().decode())
                if all(status.get(k) for k in ("mininet", "controller", "app_server", "logger")):
                    break
            except Exception:
                pass
            time.sleep(1)
        required = ("mininet", "controller", "app_server", "logger")
        if not all(status.get(k) for k in required):
            raise RuntimeError(f"Dashboard health check did not pass: {status}")

        url = "http://127.0.0.1:8000/"
        print("\n===============================================", flush=True)
        print(" SDN FIREWALL DASHBOARD IS READY", flush=True)
        print(" " + url, flush=True)
        print(" All four service checks: ONLINE", flush=True)
        print(" Keep this terminal open. Press Ctrl+C to stop.", flush=True)
        print("===============================================\n", flush=True)
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

        while True:
            for name, (proc, _log) in SERVICES.items():
                if proc.poll() is not None:
                    tail_log(name)
                    raise RuntimeError(f"{name} exited unexpectedly with code {proc.returncode}")
            time.sleep(2)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"\n[ERROR] {exc}", flush=True)
        print("The project was not declared ready. See logs/*.out for details.", flush=True)
        return 1
    finally:
        shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
