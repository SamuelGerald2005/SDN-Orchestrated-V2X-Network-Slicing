# V2X Slicing Project: Handoff Notes v2 (6 Nov 2026)

Project: **SDN-Orchestrated Network Slicing for Vehicular 5G (V2X)**
Team: A. Adharsh, Rishabh Bhat, Samuel Gerald.
Stack: Mininet-WiFi (wmediumd) + RYU 4.34 (OpenFlow 1.3) + Open vSwitch 3.5, in Docker image `mn-wifi:v2`, on native Ubuntu 24.04.

This replaces `~/Downloads/V2X_HANDOFF.md` (5 Nov). Sections 1–3 of that file (host, images, launch script) are still correct and are written up properly in `docs/Environment_Setup_Guide_Part3.pdf`. Everything below supersedes its Sections 4–9.

Status in one line: **everything in the old "next steps" is done**. The orchestrator is verified, all functional tests pass, and the full experiment (80 trials, 5 repeats) is complete and analysed. A dashboard and an evaluator explanation exist. The one open technical problem is the 7–14 s outage at each handover, which comes from the emulator's Wi-Fi re-association, not from the slicing.

---

## 1. Project files (`~/v2x-project`, now a git repository)

| Path | What it is |
|---|---|
| `controller/v2x_orchestrator.py` | The orchestrator (RYU app): slices, meters, DSCP marking, capacity loop, mobility-aware forwarding, REST on 8081 |
| `v2x_topology_v2.py` | Current topology: 2 RSUs, 6 vehicles, MEC per RSU, central servers, 3-band priority queues on the backhaul, scripted or random-waypoint mobility, beacons, position trace |
| `v2x_topology.py` | Original 2-vehicle topology (kept for history) |
| `experiments/udp_probe.py` | UDP echo probe: per-packet RTT, loss, gaps; optional live JSON for the dashboard |
| `experiments/analyze.py` | Logs → `trials.csv`, `summary.md`, `results.json` |
| `experiments/figures.py` | `results.json` → SVG figures (convert to PNG with LibreOffice) |
| `scripts/run_all_host.sh` | **One command for everything**: functional tests, Step 12 check, gate, dashboard recordings, N experiment repeats |
| `scripts/run_step2_host.sh` | Experiments only (`reps`, `"scenario list"`) |
| `scripts/verify_step12_host.sh` | Step 12 verification only |
| `scripts/run_live_demo_host.sh` | Continuous testbed for the dashboard's Live view |
| `dashboard/` | `server.py` (port 8090), `index.html`, `app.js`, `style.css`, `recordings/*.json`, `results.json` |
| `docs/` | Evaluator explanation, progress report, setup guide Part 3, figures, this file |
| `logs/` | Raw logs, git-ignored. `logs/step2` is the final experiment; `logs/final` is the final batch's functional tests and gate |

## 2. What changed since 5 Nov, and why

| Change | Why |
|---|---|
| `self.events` → `self.event_log` in the controller | It overwrote RYU's internal event queue; no switch could register |
| hostapd `ap_max_inactivity=6, skip_inactivity_poll=1, max_listen_interval=6`, plus a 1 s ping beacon from each vehicle | The old RSU kept a departed vehicle in its station table and delivered frames locally, so cross-RSU V2V failed (74/90). Settings taken from Saraiva et al.'s public code |
| `client_isolation=True` on RSUs, controller hairpins Wi-Fi→Wi-Fi traffic with `OFPP_IN_PORT` | Two vehicles on one RSU were bridged by the kernel and bypassed OVS and its meters |
| RSU `range=30` (13 dBm) | Coverage hole between the RSUs |
| **Strict-priority queues** on all four ends of both backhaul links: HTB 20 Mb/s → `prio` 3 bands → netem 5 ms per band; u32 filters on DSCP | The team update claimed strict priority but it did not exist. Also, the RSU end of each backhaul link had lost its shaping, so the uplink was unshaped |
| Controller writes DSCP in table 0 (URLLC 46, platoon 40, mMTC 18, eMBB 10) | Feeds the priority queues: 46/40 → band 1, 18 → band 2, rest → band 3 |
| **Capacity-aware loop** (`V2X_POLICY=capacity`, default) | The old rule (halve eMBB once critical ≥ 500 kb/s) ignored how much the link had left. New rule: eMBB = 20000 − critical − 1500 headroom, in 500 kb/s steps, min 2000. Events PROTECT_ON / ADJUST / PROTECT_OFF |
| **Random-waypoint mobility** (`V2X_MOBILITY=random`, `V2X_SEED`) | Claimed in the team update; added. Stations must have no fixed `position` or Mininet-WiFi treats them as parked |
| Monkeypatch `IntfWireless.cmd` to use `pexec` off the main thread | The mobility thread crashed (AssertionError) when the CLI was busy on the same node |
| Switches `V2X_PRIORITY`, `V2X_DYNAMIC`, `V2X_POLICY`, `V2X_PLOT`, `V2X_TRACE` | Needed to run the five setups and the dashboard |
| Backhaul links looked up in `net.links` after `build()` | `addLink` returns `None` in Mininet-WiFi |

## 3. Verified results

### Step 12 (orchestrator) — `logs/step12`
- 3 switches register, 5 meters and all slice rules installed, no `OFP ERROR`.
- `pingall` 90/90 three times after mobility; 4 HANDOVER events.
- Same-RSU V2V traffic now hits the platoon meter counters.

### Functional tests — `logs/final/functional`
| Test | Result |
|---|---|
| URLLC flood 10 Mb/s | 4.96 Mb/s through (limit 5) |
| mMTC flood 2 Mb/s | 0.99 Mb/s (limit 1) |
| Best-effort flood 4 Mb/s | 1.97 Mb/s (limit 2) |
| eMBB TCP | 11.27 Mb/s (limit 12) |
| REST `PUT urllc 3000` | meter shows 3000, flow gets 2.98 Mb/s; restored to 5000 |
| REST status codes | 200, 200, 404 (unknown slice), 400 (bad body) |
| Queue tree + DSCP filters | installed on s1-eth1/2, rsu1-eth3, rsu2-eth3 |

Latency: own-RSU MEC 1.2 ms, other-RSU MEC 21 ms (now that both backhaul ends are shaped), central servers 40.7 ms.

### Experiment — `logs/step2` (5 repeats, 80 trials, all valid)

Numbers are mean over repeats of the per-trial value during the eMBB flood. Full tables are in `logs/step2/summary.md`; figures are in `docs/figures`.

| Scenario, flow | Best effort | Meters only | Meters + loop | Static (meters + priority) | Orchestrated |
|---|---|---|---|---|---|
| Congestion, platoon RTT p95 | 3795 ms, 7.7 % loss | 25.5 ms | 25.5 ms | 24.9 ms | 24.9 ms |
| Congestion, URLLC edge p95 | 2380 ms | 4.8 ms | 4.8 ms | 4.8 ms | 4.7 ms |
| Heavy, platoon RTT p95 | 702 ms | 203 ms | 24.4 ms | 23.3 ms | 23.2 ms |
| Heavy, URLLC far p95 | 702 ms | 203 ms | 23.7 ms | 22.2 ms | 22.1 ms |
| Heavy, eMBB throughput | 11.5 Mb/s | 11.3 | 8.9 | 11.2 | 8.9 |
| Handover, platoon loss | 82 % | – | – | 50 % | 51 % |
| Handover, longest gap | 16.9 s | – | – | 14.2 s | 14.1 s |

- Band-1 counters confirm the marking: static/orchestrated put about 61 MB through band 1 on the backhaul in a heavy trial; best effort and meters-only put 0 there.
- In heavy runs the loop fires 3 PROTECT_ON (one per switch), then ADJUST to 9500 kb/s, then PROTECT_OFF when the critical flows stop.
- One trial (random, best effort, repeat 4) hung at teardown and lost its `events.json`; its probe data are complete and the analysis counts it with n = 4.

## 4. Known problems and limitations

1. **Handover outage of 7–14 s** in every setup. Mininet-WiFi reports the new association within a second, but traffic reaches the new RSU's switch about 6–10 s later (the RYU HANDOVER event comes at that moment). The RSUs are on different channels (1 and 6) and wpa_supplicant scans and re-associates slowly in the emulator. Slicing doesn't cause it and can't fix it; it does reduce loss around it (82 % → 50 % for platoon). Things to try: same channel on both RSUs, `bgscan`/shorter scan intervals in the station config, Mininet-WiFi's `ac_method='llf'` (not `ssf`, which broke re-association).
2. **Random-waypoint results have large spread** (standard deviation as large as the mean), because how often a vehicle is between RSUs depends on the seed. They are reported but not used for the main claims.
3. The loop measures critical load **before** the meter drops, so a flow above its own budget still counts at its offered rate.
4. Under best effort there are no meters, so the dashboard has no per-slice counters for it.
5. Random waypoint can wander a little outside `min_x`/`min_y`.
6. The 1 s beacons are best-effort traffic (about 1 kb/s per vehicle).
7. No nearest-MEC steering after handover; no SUMO (so "road-constrained" means the scripted paths).
8. `sch_htb quantum is big` and `Cannot delete qdisc with handle of zero` messages are harmless.

## 5. How to run

```bash
python3 ~/v2x-project/dashboard/server.py           # dashboard on http://127.0.0.1:8090, no sudo
sudo bash ~/v2x-project/scripts/run_live_demo_host.sh orchestrated 30   # live testbed for the dashboard
sudo bash ~/v2x-project/scripts/run_all_host.sh 5   # everything from scratch, about 3.5 h
python3 ~/v2x-project/experiments/analyze.py logs/step2 && cp logs/step2/results.json dashboard/
python3 experiments/figures.py logs/step2/results.json docs/figures
```

Docker needs `sudo` (the user isn't in the `docker` group). Every script hands file ownership back to `samuel` at the end.

## 6. Corrections to the team update (for the report and slides)

| Claim in the team update | Status now |
|---|---|
| "maps traffic flows to appropriate OVS queues and OpenFlow meters for strict priority scheduling" | **Now true**, but wording should be: OpenFlow meters police each slice; the controller sets DSCP; Linux `prio` queues on the backhaul (not OVS queues) schedule strictly by DSCP |
| "UDP 5000 directly to the highest priority URLLC queue (Queue 0)" | **Inaccurate.** There was never an OVS queue 0 for URLLC. Now: UDP 5000 → meter 1 → DSCP 46 → band 1 of the backhaul `prio` qdisc |
| "random waypoint / road-constrained mobility" | Random waypoint **now true**. "Road-constrained" only means the scripted straight paths; there is no SUMO road network |
| "dynamic reallocation" | True: capacity-aware loop plus REST resize, both measured |
| "standardised benchmarking" | True in the sense of a fixed, scripted, repeated benchmark (5 setups × 4 scenarios × 5 repeats) |
| "emulation-scale V2X slicing" | True |

## 7. Next steps

1. Fix or shorten the handover outage (Section 4.1), then rerun only the handover and random scenarios: `sudo bash scripts/run_step2_host.sh 5 "handover random"`.
2. Nearest-MEC steering after handover (rewrite the destination to the new RSU's MEC).
3. SUMO-driven mobility, if road-constrained mobility must be claimed.
4. Count critical load after the meter (or use per-slice port counters) in the loop.
5. More vehicles and RSUs to show it scales.

## 8. Literature anchors

- Saraiva et al., IEEE T-ITS 22(8) 2021: closest match; we reuse their hostapd settings and their best-effort / QoS-only / framework comparison.
- Shah et al., IEEE TCE 71(1) 2025: measuring safety traffic during handover.
- Ahmad, Gul & Derawi, Sensors 26(13) 2026: four slices, priority-weighted dynamic bandwidth.
- Campolo et al., Sensors 2018: RYU + OF1.3 metering on Mininet-WiFi.
