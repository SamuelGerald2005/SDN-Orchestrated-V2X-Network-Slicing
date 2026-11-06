# SDN-Orchestrated Network Slicing for Vehicular 5G (V2X)

Mininet-WiFi + RYU 4.34 (OpenFlow 1.3) + Open vSwitch, run in Docker on Ubuntu.
Team: A. Adharsh, Rishabh Bhat, Samuel Gerald.

Six vehicles move between two roadside units (RSUs). Each RSU has an edge (MEC)
server, and both connect over a 20 Mb/s backhaul to an aggregation switch and the
central servers. A RYU application, the orchestrator, runs five slices: it
classifies traffic, polices each slice with an OpenFlow meter, marks packets for
strict-priority queues, follows vehicles across handovers, and adapts the eMBB
budget to what the backhaul has left.

## Layout

| Path | What it is |
|---|---|
| `controller/v2x_orchestrator.py` | The orchestrator (RYU app) and its REST API on port 8081 |
| `v2x_topology_v2.py` | The topology: RSUs, vehicles, MEC and central servers, links, priority queues, mobility |
| `experiments/udp_probe.py` | Per-slice UDP probe: RTT, jitter, loss, delivery gaps |
| `experiments/analyze.py` | Turns experiment logs into `trials.csv`, `summary.md` and `results.json` |
| `experiments/figures.py`, `run_figures.py` | Report figures from `results.json` and from the dashboard recordings |
| `dashboard/` | The dashboard (`server.py`, `index.html`, `app.js`) and its recordings |
| `scripts/` | Batch scripts that run everything inside the container |
| `docker/Dockerfile` | The `mn-wifi:v2` image |
| `docs/` | `V2X_Evaluator_Explanation.pdf` (start here), `V2X_HANDOFF_v2.md`, setup guide Part 3, progress report, `figures/` |
| `logs/` | Raw logs of every run (not in git) |

## Quick start

Open the dashboard (no sudo or Docker needed; it replays recorded runs):

```bash
python3 ~/v2x-project/dashboard/server.py
```

Then open http://127.0.0.1:8090. Direct links open a chosen moment, e.g.
`/?rec=scripted_best_effort&cmp=scripted_orchestrated&t=55` or `/?view=results&scenario=heavy`.

Run the testbed live and watch it on the dashboard (two terminals):

```bash
sudo bash ~/v2x-project/scripts/run_live_demo_host.sh orchestrated 30
```

```bash
python3 ~/v2x-project/dashboard/server.py
```

Pick "Live testbed" in the Recording list. Use `best_effort` or `static` in place
of `orchestrated` to compare.

Run everything again from scratch (checks, recordings, 5 experiment repeats, about 3 hours):

```bash
sudo bash ~/v2x-project/scripts/run_all_host.sh 5
```

```bash
cd ~/v2x-project && python3 experiments/analyze.py logs/step2 && cp logs/step2/results.json dashboard/
```

Manual session, as in the original workflow (two terminals into the container):

```bash
~/start_mnwifi.sh
```

Inside it: `mn -c`, then `ryu-manager --wsapi-port 8081 /app/project/controller/v2x_orchestrator.py`.
In a second terminal, `sudo docker exec -it $(sudo docker ps -q --filter ancestor=mn-wifi:v2) bash`,
then `python3 /app/project/v2x_topology_v2.py`.

## Results (5 repeats, 95th percentile RTT during an eMBB flood)

| | Best effort | Meters only | Meters + loop | Meters + priority | Orchestrated |
|---|---|---|---|---|---|
| Congestion, platoon | 3795 ms | 25.5 ms | 25.5 ms | 24.9 ms | 24.9 ms |
| Heavy load, platoon | 702 ms | 203 ms | 24.4 ms | 23.3 ms | 23.2 ms |

Full tables: `logs/step2/summary.md` (not in git). Known limitation: a 7 to 14 s gap at each
handover in every setup, from the emulated Wi-Fi re-association (see `docs/V2X_HANDOFF_v2.md`).

## Controller switches (environment variables)

| Variable | Effect |
|---|---|
| `V2X_SLICING=0` | Best effort: no meters, no marking, no loop |
| `V2X_PRIORITY=0` | Meters but no DSCP marking, so all traffic shares one queue band |
| `V2X_DYNAMIC=0` | Threshold loop off (static budgets) |
| `V2X_POLICY=fixed` | The earlier loop policy: halve eMBB whenever critical traffic appears |

## Topology switches

| Variable | Effect |
|---|---|
| `V2X_MOBILITY=random` | Random waypoint mobility (seed `V2X_SEED`) instead of the scripted paths |
| `V2X_PLOT=0` | No live Mininet-WiFi plot |
| `V2X_TRACE=<dir>` | Write positions for the dashboard |

## REST API (port 8081)

```bash
curl -s localhost:8081/v2x/slices
```

```bash
curl -s -X PUT -d '{"kbps": 8000}' localhost:8081/v2x/slices/embb
```

```bash
curl -s localhost:8081/v2x/events
```
