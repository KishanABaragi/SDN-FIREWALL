"""Local FastAPI bridge for the SDN Firewall control room."""
from __future__ import annotations

import csv
import json
import re
import socket
import time
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
GUI = ROOT / "gui" / "frontend"
CONTROL = ("127.0.0.1", 6001)
MANAGER = ("127.0.0.1", 6003)
HOSTS = [
    {"id": "h1", "ip": "10.0.0.1", "mac": "00:00:00:00:00:01", "role": "Traffic source"},
    {"id": "h2", "ip": "10.0.0.2", "mac": "00:00:00:00:00:02", "role": "Firewall test host"},
    {"id": "h3", "ip": "10.0.0.3", "mac": "00:00:00:00:00:03", "role": "Application server · TCP 5000"},
    {"id": "h4", "ip": "10.0.0.4", "mac": "00:00:00:00:00:04", "role": "Security logger · TCP 6000"},
    {"id": "h5", "ip": "10.0.0.5", "mac": "00:00:00:00:00:05", "role": "Client"},
    {"id": "h6", "ip": "10.0.0.6", "mac": "00:00:00:00:00:06", "role": "Client"},
]
TESTS = [
    {"id": 1, "name": "TCP communication", "group": "Connectivity", "duration": "5–10 sec", "purpose": "Checks that a client can exchange messages with the application server on h3.", "checks": ["Connect from h1 to h3:5000", "Send four messages", "Count real ACK replies"]},
    {"id": 2, "name": "Traffic visibility", "group": "Monitoring", "duration": "5–10 sec", "purpose": "Generates application traffic and verifies that Open vSwitch packet counters increase.", "checks": ["Record OVS packet counters", "Generate TCP traffic", "Compare the counters and ACK replies"]},
    {"id": 3, "name": "Firewall block & recovery", "group": "Firewall", "duration": "10–15 sec", "purpose": "Temporarily blocks h2, checks that h1 cannot reach it, then removes the rule and verifies recovery.", "checks": ["Measure baseline ping", "Block h2 using its MAC address", "Verify packet loss", "Unblock h2 and verify recovery"]},
    {"id": 4, "name": "Central event logger", "group": "Monitoring", "duration": "5–10 sec", "purpose": "Checks that the application server's CONNECT and DISCONNECT events are written by the logger on h4.", "checks": ["Record current log size", "Run a client session", "Verify new CONNECT and DISCONNECT records"]},
    {"id": 5, "name": "Automatic detection & timed recovery", "group": "Detection", "duration": "About 40 sec", "purpose": "Sends repeated SYN attempts from h1 and waits for the controller's own timed UNBLOCK. No manual unblock is used to make the test pass.", "checks": ["Send 14 connection attempts", "Verify automatic BLOCK in controller CSV", "Wait for timer expiry", "Verify automatic UNBLOCK and host recovery"]},
    {"id": 6, "name": "Network performance", "group": "Performance", "duration": "5–8 sec", "purpose": "Measures live baseline packet loss and average round-trip time from h1 to h3.", "checks": ["Send five ICMP echo requests", "Read packet loss", "Read average RTT"]},
    {"id": 7, "name": "Concurrent clients", "group": "Capacity", "duration": "5–12 sec", "purpose": "Runs h1 and h2 at the same time and counts the application server's ACK replies.", "checks": ["Start two clients concurrently", "Send five messages per client", "Count up to ten ACK replies"]},
]

app = FastAPI(title="SDN Firewall Control Room", version="3.0", docs_url="/api/docs")


class FirewallRequest(BaseModel):
    mac: str
    seconds: int = Field(default=30, ge=1, le=3600)


def probe(address, timeout=0.45):
    try:
        with socket.create_connection(address, timeout=timeout):
            return True
    except OSError:
        return False


def request_json(address, payload, timeout=5):
    try:
        with socket.create_connection(address, timeout=timeout) as conn:
            conn.settimeout(timeout)
            conn.sendall(json.dumps(payload).encode())
            chunks = []
            while True:
                part = conn.recv(8192)
                if not part:
                    break
                chunks.append(part)
        return json.loads(b"".join(chunks).decode())
    except OSError as exc:
        raise HTTPException(503, f"Service {address[1]} is unavailable: {exc}")
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(502, f"Service {address[1]} returned an invalid response: {exc}")


def controller_command(action, mac, seconds=None):
    payload = f"{action} {mac}" + (f" {seconds}" if action == "BLOCK" else "")
    try:
        with socket.create_connection(CONTROL, timeout=5) as conn:
            conn.settimeout(5)
            conn.sendall((payload + "\n").encode())
            data = b""
            while b"\n" not in data and len(data) < 4096:
                part = conn.recv(1024)
                if not part:
                    break
                data += part
        return data.decode(errors="replace").strip()
    except OSError as exc:
        raise HTTPException(503, f"Ryu control interface is unavailable: {exc}")


def manager_command(payload, timeout=15):
    return request_json(MANAGER, payload, timeout)


def controller_events():
    path = ROOT / "logs/controller_events.csv"
    if not path.exists():
        return []
    try:
        with path.open(newline="", errors="replace") as stream:
            return list(csv.DictReader(stream))
    except OSError:
        return []


def current_blocks():
    latest = {}
    for row in controller_events():
        mac = row.get("mac", "").lower()
        action = row.get("action", "").upper()
        if mac and action in ("BLOCK", "UNBLOCK"):
            latest[mac] = row
    result = []
    for host in HOSTS:
        row = latest.get(host["mac"])
        if row and row.get("action", "").upper() == "BLOCK":
            seconds = int(row.get("block_seconds") or 30)
            result.append({**host, "blocked": True, "since": row.get("timestamp"), "seconds": seconds,
                           "detail": row.get("detail", "")})
    return result


@app.get("/api/health")
def health():
    return {"ok": True, "application": "SDN Firewall Control Room", "version": "3.0"}


@app.get("/api/status")
def status():
    mn = False
    manager = {"running": False, "detail": "Mininet manager is not reachable"}
    if probe(MANAGER):
        try:
            manager = manager_command({"action": "STATUS"}, 4)
            mn = bool(manager.get("running"))
        except HTTPException as exc:
            manager["detail"] = exc.detail
    ryu_control = probe(CONTROL)
    openflow = probe(("127.0.0.1", 6653))
    return {
        "mininet": mn,
        "controller": bool(ryu_control and openflow and manager.get("switch_connected")),
        "app_server": bool(manager.get("app_server")),
        "logger": bool(manager.get("logger")),
        "switch_connected": bool(manager.get("switch_connected")),
        "controller_endpoint": "127.0.0.1:6653 · control 6001",
        "app_endpoint": "h3 · 10.0.0.3:5000",
        "logger_endpoint": "h4 · 10.0.0.4:6000",
        "details": {
            "mininet": manager.get("detail", ""),
            "ryu_control": ryu_control,
            "openflow_listener": openflow,
            "switch_connected": bool(manager.get("switch_connected")),
        },
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/topology")
def topology():
    manager = manager_command({"action": "STATUS"}, 4)
    return {"hosts": HOSTS, "switch": "s1", "controller": "Ryu · OpenFlow 1.3", "connected": bool(manager.get("switch_connected")), "manager": manager}


@app.get("/api/hosts")
def hosts():
    return {"hosts": HOSTS}


@app.get("/api/tests")
def tests():
    return {"tests": TESTS}


@app.get("/api/events")
def events():
    rows: List[Dict[str, Any]] = []
    csv_path = ROOT / "logs/controller_events.csv"
    if csv_path.exists():
        for index, row in enumerate(controller_events()):
            rows.append({"id": f"controller-{index}", "source": "Controller", "timestamp": row.get("timestamp", ""),
                         "action": row.get("action", "EVENT"), "mac": row.get("mac", ""),
                         "detail": row.get("detail", ""), "result": row.get("result", ""), "raw": row})
    for path, label in [
        (ROOT / "logs/runtime_logger/security_events.log", "Network logger"),
        (ROOT / "logs/security_events.log", "Network logger"),
        (ROOT / "security_events.log", "Historical log"),
    ]:
        if path.exists():
            try:
                for index, line in enumerate(path.read_text(errors="replace").splitlines()[-400:]):
                    if not line.strip():
                        continue
                    try:
                        parsed = json.loads(line)
                        event = parsed.get("event", parsed)
                        rows.append({"id": f"{path.name}-{index}", "source": label,
                                     "timestamp": parsed.get("received_at", event.get("time", "")),
                                     "action": event.get("type", "EVENT"), "mac": event.get("src_mac", ""),
                                     "detail": event.get("detail", ""), "result": "recorded", "raw": parsed})
                    except (ValueError, AttributeError):
                        rows.append({"id": f"{path.name}-{index}", "source": label, "timestamp": "",
                                     "action": "EVENT", "mac": "", "detail": line, "result": "recorded", "raw": line})
            except OSError:
                pass
    rows.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
    return {"events": rows[:600], "count": len(rows)}


@app.get("/api/firewall/state")
def firewall_state():
    return {"blocked_hosts": current_blocks()}


@app.post("/api/firewall/block")
def block(req: FirewallRequest):
    mac = req.mac.lower()
    if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", mac):
        raise HTTPException(400, "Select a valid host MAC address.")
    response = controller_command("BLOCK", mac, req.seconds)
    accepted = response.lower().startswith("blocked") or response.lower().startswith("already blocked")
    return {"ok": accepted, "response": response, "mac": mac, "seconds": req.seconds,
            "requested_at": time.time(), "expires_at": time.time() + req.seconds if accepted and response.lower().startswith("blocked") else None}


@app.post("/api/firewall/unblock")
def unblock(req: FirewallRequest):
    mac = req.mac.lower()
    if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", mac):
        raise HTTPException(400, "Select a valid host MAC address.")
    response = controller_command("UNBLOCK", mac)
    return {"ok": response.lower().startswith("unblocked") or response.lower().startswith("not blocked"), "response": response, "mac": mac}


@app.post("/api/tests/run-all")
def run_all():
    results = []
    for test in TESTS:
        action = {1: "TOPOLOGY", 2: "CLASSIFICATION", 3: "FIREWALL", 4: "LOGGING", 5: "AUTOMATIC", 6: "PERFORMANCE", 7: "MULTICLIENT"}[test["id"]]
        try:
            result = manager_command({"action": "TEST", "test": action}, 58 if test["id"] == 5 else 25)
            result.update({"test_id": test["id"], "name": test["name"], "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
        except HTTPException as exc:
            result = {"test_id": test["id"], "name": test["name"], "status": "ERROR", "summary": str(exc.detail), "steps": [], "evidence": []}
        results.append(result)
    return {"results": results, "completed_at": time.strftime("%Y-%m-%d %H:%M:%S")}


@app.post("/api/tests/{test_id}")
def run_test(test_id: int):
    test = next((item for item in TESTS if item["id"] == test_id), None)
    if not test:
        raise HTTPException(404, "Unknown test.")
    action = {1: "TOPOLOGY", 2: "CLASSIFICATION", 3: "FIREWALL", 4: "LOGGING", 5: "AUTOMATIC", 6: "PERFORMANCE", 7: "MULTICLIENT"}[test_id]
    result = manager_command({"action": "TEST", "test": action}, 58 if test_id == 5 else 25)
    result.update({"test_id": test_id, "name": test["name"], "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
    return result

@app.get("/")
def home():
    return FileResponse(GUI / "index.html")


app.mount("/assets", StaticFiles(directory=str(GUI / "assets"), check_dir=False), name="assets")
