# NCC paper: Capacity-Aware SDN Orchestration of V2X Network Slices

Overleaf-ready source. Upload `ncc_paper_overleaf.zip` (New Project → Upload Project); main file `main.tex`,
compiler pdfLaTeX. Every figure is drawn in TikZ/pgfplots from the CSV files in `data/`, so all data and
figure sources are inside the project (no AI-generated or pasted images).

| Path | Contents |
|---|---|
| `main.tex` | The manuscript (IEEEtran conference format) |
| `refs.bib` | 13 references, numbered in order of first citation |
| `figures/architecture.tex` | Fig. 1, testbed architecture (TikZ) |
| `figures/pipeline.tex` | Fig. 2, per-switch pipeline and priority queue (TikZ) |
| `figures/rtt_bars.tex` | Fig. 3, 95th-percentile RTT, congestion and heavy load (pgfplots ← `data/congestion_p95.csv`, `data/heavy_p95.csv`) |
| `figures/embb_tput.tex` | Fig. 4, eMBB throughput (← `data/embb_tput.csv`) |
| `figures/timeline.tex` | Fig. 5, one run second by second (← `data/timeline_*.csv`) |
| `figures/mobility_loss.tex` | Fig. 6, loss under mobility (← `data/handover_loss.csv`, `data/random_loss.csv`) |
| `data/trials.csv` | Raw per-trial metrics for all 80 trials (one row per trial, flow and window) |
| `data/summary_all.csv`, `data/summary.md` | Mean and standard deviation over the 5 repetitions, every scenario, setup and flow |
| `data/make_data.py` | Regenerates the plot CSVs from `results/results.json` and the dashboard recordings |

Raw packet logs of every trial (per-packet RTT CSVs, controller events, meter and queue counters) are in
`logs/step2/` of the project repository; they are too large for Overleaf.

Before submission: check author names, order and e-mails (the guide's e-mail is not filled in), and verify each
reference against its publisher page.
