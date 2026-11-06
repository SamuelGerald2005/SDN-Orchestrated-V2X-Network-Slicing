# Speaker notes: V2X Evaluation II deck

About 20 minutes plus questions. Slides 1–5, 7 and 9 are unchanged from Evaluation I (apart from the
title "EVALUATION II" and slide 9's heading). Numbers come from `results/summary.md` (5 repeats).

| # | Slide | What to say |
|---|---|---|
| 1–5 | Title, objective, literature, gaps | As in Evaluation I. Keep it to 3 minutes. |
| 6 | What we built | The four mechanisms. The headline number: platoon delay 3.8 s → 25 ms under a flood, 0 % loss. |
| 7 | Proposed design | The concept picture: one controller, two RSUs, safety and infotainment separated. |
| 8 | Architecture & pipeline | Bottom row: classify → police → mark → forward → priority queue. The loop feeds the meters. |
| 9 | Topology | 6 vehicles, 2 RSUs on channels 1 and 6, MEC per RSU, central servers 15 ms away. |
| 10 | Slice configuration | Read one row: UDP 5000 → meter 1 at 5 Mb/s → DSCP 46 → band 1. **Say the correction out loud**: Evaluation I said "OVS queue 0"; the real mechanism is meter + DSCP + Linux priority queues. |
| 11 | Enforcement | Meters are exact (10 → 4.96 Mb/s). Priority proven by counters: 61 MB in band 1 with marking, 0 without. Budgets sum to 24 Mb/s on a 20 Mb/s link, so both are needed. |
| 12 | Capacity loop | The formula, then the three events seen in every heavy trial. REST PUT works live. |
| 13 | Mobility fixes | Three real bugs we found and fixed; the first fix comes from Saraiva et al.'s code. |
| 14 | Edge vs central | 1.2 ms to the own MEC vs 40.7 ms central: the evaluator's earlier request for an edge server. |
| 15 | Experiment design | Each setup adds one mechanism; that is what makes the comparison meaningful. 80 trials. |
| 16 | Congestion | Best effort seconds of delay and 8–10 % loss; any slicing ~25 ms, 0 % loss. |
| 17 | Heavy load | **The key slide.** Meters alone 203 ms. Loop 24 ms (costs eMBB 2.3 Mb/s), priority 23 ms, both 23 ms. |
| 18 | One run | The dashboard recording: same run with and without the orchestrator. Good moment to switch to the live demo. |
| 19 | Handover | Be upfront: 7–14 s gaps in every setup, caused by the emulated Wi-Fi re-association, not by slicing. Slicing still halves loss. |
| 20 | Dashboard | Demo order: How it works → Run (best effort vs orchestrated, speed 4) → Results (heavy). |
| 21 | Summary | Four contributions, four numbers. |
| 22 | Milestones | All planned tasks done, plus the dashboard and full benchmark. |
| 23 | Limitations & future work | Handover gap first; then nearest-MEC steering, SUMO, scale, loop input. |
| 24–25 | References, questions | Likely questions and answers are in section 9 of `V2X_Evaluator_Explanation.pdf`. |

Rebuild the deck after changes: `bash docs/report_src/deck/pack.sh` (expects the template at
`tpl/template.pptx` next to the script; it is a 62 MB file kept out of git).
