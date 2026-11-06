#!/usr/bin/env python3
"""Exports the data behind every plot in the paper as small CSV files (pgfplots reads them).
  python3 paper/data/make_data.py          (run from the project root)
Inputs: results/results.json (analysis of 80 trials, logs/step2) and dashboard/recordings/*.json."""
import csv
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.dirname(os.path.abspath(__file__))
SETUPS = ['best_effort', 'meters_only', 'meters_loop', 'static', 'orchestrated']
FLOWS = ['urllc_edge', 'urllc_far', 'platoon', 'mmtc']

res = json.load(open(os.path.join(ROOT, 'results', 'results.json')))


def group(scen, flow, win, setup):
    for g in res['groups']:
        if g['scenario'] == scen and g['flow'] == flow and g['setup'] == setup and (g['window'] == win or flow == 'embb'):
            return g
    return None


def val(g, key):
    if not g or not g.get(key) or g[key]['mean'] is None:
        return 'nan', 'nan'
    return '%.4g' % g[key]['mean'], '%.4g' % (g[key]['sd'] or 0)


def bars(scen, win, key, setups, name, flows=FLOWS):
    """One row per flow, mean and sd columns per setup (pgfplots grouped bars)."""
    with open(os.path.join(OUT, name), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['flow'] + [c for s in setups for c in (s, s + '_sd')])
        for fl in flows:
            row = [fl]
            for s in setups:
                row += val(group(scen, fl, win, s), key)
            w.writerow(row)


bars('congestion', 'load', 'rtt_p95', SETUPS, 'congestion_p95.csv')
bars('heavy', 'load', 'rtt_p95', SETUPS, 'heavy_p95.csv')
bars('handover', 'moving', 'loss_pct', ['best_effort', 'static', 'orchestrated'], 'handover_loss.csv', flows=FLOWS[:3])
bars('random', 'load', 'loss_pct', ['best_effort', 'static', 'orchestrated'], 'random_loss.csv')

# eMBB throughput per setup in the two parked scenarios (Mb/s)
with open(os.path.join(OUT, 'embb_tput.csv'), 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['setup', 'congestion', 'congestion_sd', 'heavy', 'heavy_sd'])
    for s in SETUPS:
        row = [s]
        for scen in ('congestion', 'heavy'):
            g = group(scen, 'embb', 'load', s)
            row += ['%.3f' % (g['kbps']['mean'] / 1000), '%.3f' % ((g['kbps']['sd'] or 0) / 1000)]
        w.writerow(row)

# Every setup and flow: loss, rate, RTT mean/p95/p99, jitter, longest gap (mean and sd over repeats)
with open(os.path.join(OUT, 'summary_all.csv'), 'w', newline='') as f:
    w = csv.writer(f)
    keys = ['loss_pct', 'kbps', 'rtt_mean', 'rtt_p95', 'rtt_p99', 'jitter_ms', 'outage_ms']
    w.writerow(['scenario', 'window', 'flow', 'setup', 'n'] + [c for k in keys for c in (k, k + '_sd')])
    for g in res['groups']:
        w.writerow([g['scenario'], g['window'], g['flow'], g['setup'], g['n']] + [c for k in keys for c in val(g, k)])

# Per-second 95th percentile RTT from the two scripted dashboard recordings
for name in ('scripted_best_effort', 'scripted_orchestrated'):
    rec = json.load(open(os.path.join(ROOT, 'dashboard', 'recordings', name + '.json')))
    flows = ['urllc_veh1', 'urllc_veh4', 'platoon', 'mmtc']
    with open(os.path.join(OUT, 'timeline_%s.csv' % name.split('_', 1)[1]), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['t'] + flows)
        for fr in rec['frames']:
            if fr['t'] < 0:
                continue
            row = ['%.1f' % fr['t']]
            for fl in flows:
                p = (fr.get('probes') or {}).get(fl)
                ok = p and p.get('received') and p.get('rtt_p95') is not None
                row.append('%.3f' % p['rtt_p95'] if ok else 'nan')
            w.writerow(row)
print('data written to', OUT)
