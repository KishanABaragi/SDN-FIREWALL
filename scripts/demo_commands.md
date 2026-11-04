# Copy/paste demo commands — all 7 points

Open a terminal in the extracted package directory. Build once:

```bash
./build.sh
```

## Terminal A — controller (Points 3, 5, 6, 7)

```bash
./scripts/run_controller.sh
```

Wait for `Control interface listening on 127.0.0.1:6001`.

## Terminal B — Mininet (Points 2, 3, 5, 6, 7)

```bash
./scripts/start_topology.sh
```

At the `mininet>` prompt, start the event logger and application server (replace `/ABS/PATH/TO/SDN_Full_D1` with the output of `pwd` from the package directory):

```text
h4 /ABS/PATH/TO/SDN_Full_D1/src/logger_server 6000 > /tmp/logger.out 2>&1 &
h3 /ABS/PATH/TO/SDN_Full_D1/src/app_server 5000 10.0.0.4 6000 > /tmp/app_server.out 2>&1 &
pingall
```

## Point 1 — TCP socket communication

```text
h1 /ABS/PATH/TO/SDN_Full_D1/src/client 10.0.0.3 5000 5 0.2
```

Expected: connection succeeds, each message receives `ACK: ...`, and RTT values are printed.

## Point 2 — traffic identification/classification

```text
h1 ip addr show h1-eth0
h1 ip route
h1 ip neigh
```

Show the controller learning source MAC/IP information and the server logging client IP/ephemeral TCP port. For OpenFlow rules:

```text
sh ovs-ofctl -O OpenFlow13 dump-flows s1
```

## Point 3 — SDN dynamic firewall

From a separate ordinary Ubuntu terminal, run the control script (MACs are stable in this topology):

```bash
./scripts/control.sh BLOCK 00:00:00:00:00:02 20
```

## Point 4 — centralized event logger

While clients connect and disconnect, inspect logger output from Mininet:

```text
h4 sh tail -n 20 security_events.log
```

The app server emits CONNECT/DISCONNECT JSON events to the logger. Controller events are also written to `logs/controller_events.csv`. Whether the controller can reach the Mininet logger at `10.0.0.4` depends on the VM's root-to-Mininet networking; verify that controller events appear in `security_events.log` before claiming controller-to-central-logger integration is demonstrated.

## Point 5 — block and automatic timed recovery

With the block command above running, test:

```text
h1 ping -c 5 h2
h1 ping -c 5 h3
```

During the timed block, h2 should be isolated while h3 remains reachable. Wait until the configured timer expires, then:

```text
h1 ping -c 5 h2
```

Expected: h2 connectivity returns after automatic rule removal. To demonstrate manual recovery instead:

```bash
./scripts/control.sh BLOCK 00:00:00:00:00:02 60
./scripts/control.sh UNBLOCK 00:00:00:00:00:02
```

## Point 6 — blocking response time and network impact

Record baseline:

```text
h1 ping -c 10 h3
h1 /ABS/PATH/TO/SDN_Full_D1/src/client 10.0.0.3 5000 10 0.2
```

Block h2, repeat `h1 ping -c 10 h3`, then test h1 to h2 during the block and after recovery. Save output for each phase. Controller `duration_ms` records rule-submission duration only; it is not end-to-end enforcement time. To measure end-to-end response time, timestamp the block command and the first observed failed probe, using the same probe method in repeated trials.

## Point 7 — multiple clients

At the `mininet>` prompt, start clients concurrently:

```text
h1 /ABS/PATH/TO/SDN_Full_D1/src/client 10.0.0.3 5000 15 0.2 > /tmp/h1-client.log 2>&1 &
h2 /ABS/PATH/TO/SDN_Full_D1/src/client 10.0.0.3 5000 15 0.2 > /tmp/h2-client.log 2>&1 &
h5 /ABS/PATH/TO/SDN_Full_D1/src/client 10.0.0.3 5000 15 0.2 > /tmp/h5-client.log 2>&1 &
h6 /ABS/PATH/TO/SDN_Full_D1/src/client 10.0.0.3 5000 15 0.2 > /tmp/h6-client.log 2>&1 &
sleep 5
h3 sh cat /tmp/app_server.out
```

If a shell command does not expand `~` or relative paths inside Mininet, use the absolute package path as shown.

## Evidence and shutdown

```text
sh ovs-ofctl -O OpenFlow13 dump-flows s1
h4 sh tail -n 30 security_events.log
exit
```

In the ordinary Ubuntu terminal:

```bash
tail -n 30 logs/controller_events.csv
```

Stop Ryu with Ctrl+C. `sudo mn -c` cleans Mininet processes; it does not delete package files. Save fresh screenshots from your own run in `evidence/fresh_run/` and keep historical screenshots clearly labelled as historical.
