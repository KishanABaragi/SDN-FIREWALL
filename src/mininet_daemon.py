#!/usr/bin/env python3
"""Root-owned Mininet manager for one-command SDN demo startup."""
import json, os, socket, subprocess, threading, time, traceback, shlex
from pathlib import Path
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.log import setLogLevel
from topology import FirewallTopo

ROOT = Path(__file__).resolve().parents[1]
HOST, PORT = "127.0.0.1", 6003
net = None
app_proc = logger_proc = None
server = None
running = True
lock = threading.Lock()

def run_host(host, command, timeout=12):
    return host.cmd("timeout %s bash -lc %s 2>&1" % (timeout, shlex.quote(command)))

def host_port_listening(host, port):
    output = host.cmd("ss -lnt 2>/dev/null")
    return (":" + str(port)) in output

def start_services():
    global app_proc, logger_proc
    (ROOT/"logs/runtime_logger").mkdir(parents=True, exist_ok=True)
    (ROOT/"logs").mkdir(exist_ok=True)
    logger_log = open(ROOT/"logs/logger_server.out","ab",buffering=0)
    app_log = open(ROOT/"logs/app_server.out","ab",buffering=0)
    logger_proc = net.get("h4").popen([str(ROOT/"src/logger_server"),"6000"],
        cwd=str(ROOT/"logs/runtime_logger"), stdout=logger_log, stderr=subprocess.STDOUT)
    app_proc = net.get("h3").popen([str(ROOT/"src/app_server"),"5000","10.0.0.4","6000"],
        cwd="/tmp", stdout=app_log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        app_ready = app_proc.poll() is None and host_port_listening(net.get("h3"), 5000)
        logger_ready = logger_proc.poll() is None and host_port_listening(net.get("h4"), 6000)
        if app_ready and logger_ready:
            print("[MININET-MANAGER] application server h3:5000 and logger h4:6000 are listening", flush=True)
            return
        time.sleep(0.5)
    raise RuntimeError("Application server h3:5000 or logger h4:6000 failed to start; inspect logs/app_server.out and logs/logger_server.out")

def ovs_diagnostic():
    """Return useful OVS state for startup logs without hiding command errors."""
    parts = []
    for label, command in (
        ("bridge", ["ovs-vsctl", "show"]),
        ("controller target", ["ovs-vsctl", "get-controller", "s1"]),
        ("controller state", ["ovs-vsctl", "list", "Controller"]),
        ("OpenFlow features", ["ovs-ofctl", "-O", "OpenFlow13", "show", "s1"]),
    ):
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=4)
            parts.append(f"--- {label} (exit {result.returncode}) ---\n{result.stdout}{result.stderr}")
        except Exception as exc:
            parts.append(f"--- {label} ---\n{exc}")
    return "\n".join(parts)


def configure_controller():
    """Explicitly apply the Ryu target after Mininet creates the OVS bridge.

    Mininet's RemoteController normally performs this configuration during
    net.start(). Reasserting it here avoids depending on timing or stale OVS
    controller rows left by a previous interrupted run.
    """
    commands = (
        ["ovs-vsctl", "set", "bridge", "s1", "protocols=OpenFlow13"],
        ["ovs-vsctl", "set-fail-mode", "s1", "secure"],
        ["ovs-vsctl", "set-controller", "s1", "tcp:127.0.0.1:6653"],
    )
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        if result.returncode:
            raise RuntimeError(f"OVS configuration failed: {' '.join(command)}\n{result.stderr}")


def controller_connected():
    try:
        result = subprocess.run(
            ["ovs-vsctl", "list", "Controller"], capture_output=True,
            text=True, timeout=3, check=True)
        import re
        return bool(re.search(r"is_connected\s*:\s*true", result.stdout, re.I))
    except Exception:
        return False

def status():
    if net is None: return {"running":False,"detail":"Mininet not started","app_server":False,"logger":False}
    connected = controller_connected()
    app_ready = bool(app_proc and app_proc.poll() is None and host_port_listening(net.get("h3"), 5000))
    logger_ready = bool(logger_proc and logger_proc.poll() is None and host_port_listening(net.get("h4"), 6000))
    return {"running":True,"detail":"Six-host Mininet topology active; switch/controller state checked separately",
            "hosts":[h.name for h in net.hosts],"switch":"s1","switch_connected":connected,
            "app_server":app_ready,"logger":logger_ready}

def _controller_command(action, mac, seconds=None):
    payload = f"{action} {mac}" + (f" {seconds}" if action == "BLOCK" and seconds else "")
    with socket.create_connection(("127.0.0.1", 6001), timeout=4) as conn:
        conn.settimeout(4)
        conn.sendall((payload + "\n").encode())
        return conn.recv(4096).decode(errors="replace").strip()


def _read_controller_events():
    import csv
    path = ROOT / "logs/controller_events.csv"
    if not path.exists():
        return []
    try:
        with path.open(newline="", errors="replace") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _ping(host, target, count=3):
    output = host.cmd(f"ping -n -c {count} -W 1 {target} 2>&1")
    import re
    match = re.search(r"([0-9.]+)% packet loss", output)
    loss = float(match.group(1)) if match else None
    rtt = re.search(r"=\s*([0-9.]+)/([0-9.]+)/([0-9.]+)/", output)
    avg = float(rtt.group(2)) if rtt else None
    return output, loss, avg


def _port_packet_total():
    result = subprocess.run(["ovs-ofctl", "-O", "OpenFlow13", "dump-ports", "s1"],
                            capture_output=True, text=True, timeout=5)
    import re
    values = [int(x) for x in re.findall(r"(?:rx|tx) pkts=(\d+)", result.stdout)]
    return sum(values), result.stdout + result.stderr


def execute(test):
    global net
    if net is None:
        return {"status":"ERROR", "summary":"The virtual network is not running.", "steps":[], "evidence":[]}
    h1, h2, h3, h4 = [net.get(x) for x in ("h1", "h2", "h3", "h4")]
    steps, evidence = [], []

    def step(label, detail, ok=None):
        steps.append({"label":label, "detail":detail, "state":"passed" if ok is True else "failed" if ok is False else "info"})

    if test == "TOPOLOGY":
        try:
            connected = controller_connected()
            target = subprocess.run(["ovs-vsctl", "get-controller", "s1"], capture_output=True, text=True, timeout=4)
            hosts = [h.name for h in net.hosts]
            ok = len(hosts) == 6 and connected and target.returncode == 0 and "6653" in target.stdout
            step("Six virtual hosts", ", ".join(hosts), len(hosts) == 6)
            step("Open vSwitch bridge", "s1 is present and managed by OVS", target.returncode == 0)
            step("Ryu OpenFlow connection", "Connected on 127.0.0.1:6653" if connected else "No active OpenFlow connection", connected)
            evidence.append(target.stdout.strip())
            return {"status":"PASS" if ok else "FAIL", "summary":"Topology and controller connection " + ("are ready." if ok else "did not meet all checks."), "steps":steps, "evidence":evidence}
        except Exception as exc:
            return {"status":"ERROR", "summary":str(exc), "steps":steps, "evidence":evidence}

    if test in ("CLASSIFICATION", "LOGGING"):
        logpath = ROOT / "logs/runtime_logger/security_events.log"
        before = logpath.stat().st_size if logpath.exists() else 0
        try:
            output = h1.cmd(f"timeout 12 {ROOT}/src/client 10.0.0.3 5000 4 0.1 2>&1")
            time.sleep(.5)
            after = logpath.stat().st_size if logpath.exists() else 0
            log_text = logpath.read_text(errors="replace") if logpath.exists() else ""
            new_log = log_text[before:]
            ack_count = output.count("ACK:")
            if test == "CLASSIFICATION":
                total_before, _ = _port_packet_total()
                # A short additional exchange creates measurable traffic for the OVS counters.
                extra = h1.cmd(f"timeout 8 {ROOT}/src/client 10.0.0.3 5000 2 0.1 2>&1")
                total_after, stats = _port_packet_total()
                evidence.extend([output[-2500:], extra[-1500:], stats[-2500:]])
                ok = ack_count >= 3 and total_after > total_before
                step("Generate TCP application traffic", f"Client received {ack_count}/4 ACK replies.", ack_count >= 3)
                step("Observe switch counters", f"OVS packet counters changed from {total_before} to {total_after}.", total_after > total_before)
                summary = "Traffic was exchanged and observed in OVS counters." if ok else "Traffic visibility could not be fully verified."
            else:
                has_connect = '"type":"CONNECT"' in new_log or '"type": "CONNECT"' in new_log
                has_disconnect = '"type":"DISCONNECT"' in new_log or '"type": "DISCONNECT"' in new_log
                ok = ack_count >= 3 and after > before and has_connect and has_disconnect
                evidence.extend([output[-2500:], new_log[-2500:]])
                step("Exchange messages with h3", f"Client received {ack_count}/4 ACK replies.", ack_count >= 3)
                step("Check logger file", f"Log size changed from {before} to {after} bytes.", after > before)
                step("Verify connection events", "CONNECT and DISCONNECT records found." if has_connect and has_disconnect else "Expected connection records were not both found.", has_connect and has_disconnect)
                summary = "The logger recorded the client connection lifecycle." if ok else "The expected logger records were not fully verified."
            return {"status":"PASS" if ok else "FAIL", "summary":summary, "steps":steps, "evidence":evidence}
        except Exception as exc:
            return {"status":"ERROR", "summary":str(exc), "steps":steps, "evidence":evidence}

    if test == "FIREWALL":
        mac = "00:00:00:00:00:02"
        try:
            _controller_command("UNBLOCK", mac)
            time.sleep(.5)
            baseline, baseline_loss, _ = _ping(h1, "10.0.0.2", 3)
            block_reply = _controller_command("BLOCK", mac, 8)
            time.sleep(.8)
            blocked, blocked_loss, _ = _ping(h1, "10.0.0.2", 3)
            unblock_reply = _controller_command("UNBLOCK", mac)
            time.sleep(.8)
            recovered, recovered_loss, _ = _ping(h1, "10.0.0.2", 3)
            ok = baseline_loss is not None and baseline_loss < 100 and blocked_loss == 100 and recovered_loss is not None and recovered_loss < 100
            step("Baseline reachability", f"h1 → h2 packet loss: {baseline_loss}%.", baseline_loss is not None and baseline_loss < 100)
            step("Apply firewall rule", block_reply, "Blocked" in block_reply)
            step("Verify blocked traffic", f"h1 → h2 packet loss: {blocked_loss}%.", blocked_loss == 100)
            step("Remove firewall rule", unblock_reply, "Unblocked" in unblock_reply)
            step("Verify recovery", f"h1 → h2 packet loss: {recovered_loss}%.", recovered_loss is not None and recovered_loss < 100)
            evidence.extend([baseline, blocked, recovered])
            return {"status":"PASS" if ok else "FAIL", "summary":"Blocking and recovery " + ("were verified with ping measurements." if ok else "did not match the expected reachability changes."), "steps":steps, "evidence":evidence}
        except Exception as exc:
            try: _controller_command("UNBLOCK", mac)
            except Exception: pass
            return {"status":"ERROR", "summary":str(exc), "steps":steps, "evidence":evidence}

    if test == "AUTOMATIC":
        mac = "00:00:00:00:00:01"
        try:
            _controller_command("UNBLOCK", mac)
            before = len(_read_controller_events())
            step("Prepare test host", "h1 is the traffic source; automatic threshold is 12 SYN attempts in 10 seconds.", True)
            command = "for i in $(seq 1 14); do (echo > /dev/tcp/10.0.0.3/5000) >/dev/null 2>&1 || true; sleep 0.08; done"
            generated = h1.cmd("timeout 12 bash -lc " + shlex.quote(command) + " 2>&1")
            step("Generate repeated TCP connection attempts", "Sent 14 connection attempts from h1 to h3:5000.", True)
            block_event = None
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                rows = _read_controller_events()[before:]
                block_event = next((r for r in rows if r.get("action", "").upper() == "BLOCK" and r.get("mac", "").lower() == mac and "automatic" in r.get("detail", "").lower()), None)
                if block_event: break
                time.sleep(.25)
            if not block_event:
                step("Automatic detection", "No matching automatic BLOCK record appeared in the controller CSV.", False)
                return {"status":"INCONCLUSIVE", "summary":"The trigger was sent, but automatic detection was not confirmed in the controller log. No PASS is claimed.", "steps":steps, "evidence":[generated[-2000:]]}
            seconds = int(block_event.get("block_seconds") or 30)
            step("Automatic block confirmed", f"Controller logged BLOCK for h1 with a {seconds}-second timeout.", True)
            step("Wait for controller timer", f"Waiting up to {seconds + 8} seconds for the controller's own timer. No manual unblock is sent.", None)
            unblock_event = None
            deadline = time.monotonic() + seconds + 8
            while time.monotonic() < deadline:
                rows = _read_controller_events()[before:]
                unblock_event = next((r for r in rows if r.get("action", "").upper() == "UNBLOCK" and r.get("mac", "").lower() == mac and "automatic" in (r.get("result", "") + r.get("detail", "")).lower()), None)
                if unblock_event: break
                time.sleep(.5)
            if not unblock_event:
                # Emergency recovery only after declaring timer verification failure.
                try: _controller_command("UNBLOCK", mac)
                except Exception: pass
                step("Automatic timer expiry", "No automatic UNBLOCK record appeared before the verification deadline. A manual safety recovery was attempted afterward.", False)
                return {"status":"FAIL", "summary":"Automatic blocking occurred, but automatic timer-based unblocking was not verified. A safety recovery was attempted after the timeout.", "steps":steps, "evidence":[generated[-2000:], str(block_event)]}
            step("Automatic timer expiry", "Controller logged automatic UNBLOCK after the configured timeout.", True)
            time.sleep(.5)
            recovery, loss, _ = _ping(h1, "10.0.0.3", 3)
            step("Confirm host recovery", f"h1 → h3 packet loss after expiry: {loss}%.", loss is not None and loss < 100)
            evidence.extend([generated[-1500:], str(block_event), str(unblock_event), recovery])
            ok = loss is not None and loss < 100
            return {"status":"PASS" if ok else "FAIL", "summary":"Automatic detection, timer expiry and post-expiry recovery " + ("were verified." if ok else "were logged, but network recovery was not confirmed."), "steps":steps, "evidence":evidence}
        except Exception as exc:
            try: _controller_command("UNBLOCK", mac)
            except Exception: pass
            return {"status":"ERROR", "summary":str(exc), "steps":steps, "evidence":evidence}

    if test == "PERFORMANCE":
        try:
            output, loss, avg = _ping(h1, "10.0.0.3", 5)
            ok = loss is not None and loss < 100
            step("Measure baseline reachability", f"h1 → h3 packet loss: {loss}%.", ok)
            step("Measure average round-trip time", f"Average RTT: {avg} ms." if avg is not None else "RTT summary was not available in ping output.", avg is not None)
            return {"status":"PASS" if ok else "FAIL", "summary":"Baseline network measurements collected from live ping output." if ok else "The target did not respond to the baseline ping.", "metrics":{"packet_loss_percent":loss,"average_rtt_ms":avg}, "steps":steps, "evidence":[output[-3000:]]}
        except Exception as exc:
            return {"status":"ERROR", "summary":str(exc), "steps":steps, "evidence":evidence}

    if test == "MULTICLIENT":
        cmd = [str(ROOT/"src/client"), "10.0.0.3", "5000", "5", "0.1"]
        p1 = h1.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        p2 = h2.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            o1, _ = p1.communicate(timeout=12)
            o2, _ = p2.communicate(timeout=12)
        except subprocess.TimeoutExpired:
            p1.kill(); p2.kill()
            return {"status":"ERROR", "summary":"Concurrent clients exceeded the 12-second test limit.", "steps":steps, "evidence":[]}
        count = o1.count("ACK:") + o2.count("ACK:")
        ok = count >= 8
        step("Start two clients together", "h1 and h2 connected to the application server on h3:5000.", True)
        step("Count server acknowledgements", f"Received {count}/10 ACK replies across both clients.", ok)
        return {"status":"PASS" if ok else "FAIL", "summary":f"Concurrent clients received {count} of 10 expected acknowledgements.", "metrics":{"acknowledgements":count,"expected":10}, "steps":steps, "evidence":[(o1+"\n"+o2)[-4000:]]}

    return {"status":"ERROR", "summary":"Unknown test identifier.", "steps":[], "evidence":[]}

def handle(conn):
    try:
        raw=conn.recv(8192).decode(errors="replace").strip()
        req=json.loads(raw)
        action=req.get("action")
        if action == "STATUS":
            # Status must remain responsive while a longer test is running.
            result = status()
        elif action == "TEST":
            with lock:
                result = execute(req.get("test", ""))
        elif action == "STOP":
            result = {"stopping": True}
            threading.Thread(target=shutdown, daemon=True).start()
        else:
            result = {"error": "Unknown action"}
        conn.sendall(json.dumps(result).encode())
    except Exception as e:
        try: conn.sendall(json.dumps({"status":"ERROR","detail":str(e)}).encode())
        except OSError: pass
    finally: conn.close()

def shutdown():
    global net, server, running
    running = False
    time.sleep(.2)
    if server is not None:
        try:
            server.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            server.close()
        except OSError:
            pass
        server = None
    try:
        if app_proc and app_proc.poll() is None: app_proc.terminate()
        if logger_proc and logger_proc.poll() is None: logger_proc.terminate()
        if net: net.stop()
    finally:
        net = None

def main():
    global net, server, running
    setLogLevel("warning")
    if os.geteuid()!=0: raise SystemExit("Run this manager with sudo.")
    net=Mininet(topo=FirewallTopo(),controller=None,autoSetMacs=False)
    net.addController("c0",controller=RemoteController,ip="127.0.0.1",port=6653)
    net.start()
    print("[MININET-MANAGER] topology created; applying explicit OpenFlow 1.3 controller configuration...", flush=True)
    configure_controller()
    print("[MININET-MANAGER] configured s1 -> tcp:127.0.0.1:6653; waiting for OpenFlow handshake...", flush=True)
    deadline = time.monotonic() + 45
    last_diagnostic = 0.0
    while time.monotonic() < deadline:
        if controller_connected():
            break
        now = time.monotonic()
        if now - last_diagnostic >= 10:
            print(ovs_diagnostic(), flush=True)
            last_diagnostic = now
        time.sleep(0.5)
    if not controller_connected():
        print("[MININET-MANAGER] OpenFlow handshake failed; final OVS diagnostics:", flush=True)
        print(ovs_diagnostic(), flush=True)
        raise RuntimeError("OpenFlow switch s1 did not establish a connection to Ryu at 127.0.0.1:6653")
    print("[MININET-MANAGER] switch s1 connected to Ryu using OpenFlow 1.3", flush=True)
    start_services()
    server=socket.socket(); server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    server.bind((HOST,PORT)); server.listen(10)
    print("[MININET-MANAGER] topology ready; manager on 127.0.0.1:6003",flush=True)
    while running:
        try:
            c,_=server.accept()
        except OSError:
            if not running: break
            raise
        threading.Thread(target=handle,args=(c,),daemon=True).start()

if __name__=="__main__": main()
