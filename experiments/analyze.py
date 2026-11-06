#!/usr/bin/env python3
"""Summarises logs/step2 into trials.csv (one row per flow per window per trial)
and summary.md (mean and standard deviation across repeats). Standard library only."""
import csv
import glob
import json
import os
import statistics as st
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'logs', 'step2')
SIZES = {'congestion': {'urllc_edge': 200, 'urllc_far': 200, 'platoon': 1000, 'mmtc': 200},
         'random': {'urllc_edge': 200, 'urllc_far': 200, 'platoon': 1000, 'mmtc': 200},
         'heavy': {'urllc_edge': 200, 'urllc_far': 1000, 'platoon': 1000, 'mmtc': 200},
         'handover': {'urllc_edge': 200, 'urllc_far': 200, 'platoon': 1000}}
SETUPS = ['best_effort', 'meters_only', 'meters_loop', 'static', 'orchestrated']


def pct(values, p):
    return sorted(values)[min(int(len(values) * p / 100), len(values) - 1)]


def window_stats(rows, lo, hi, size):
    rows = [r for r in rows if lo <= r[0] < hi]
    if not rows:
        return None
    rtts = [r[1] for r in rows if r[1] is not None]
    got = [r[0] for r in rows if r[1] is not None]
    # Longest gap between delivered probes: the outage a vehicle would notice
    edges = [lo] + got + [hi]
    out = {'sent': len(rows), 'loss_pct': 100 * (1 - len(rtts) / len(rows)),
           'kbps': len(rtts) * size * 8 / 1000 / (hi - lo),
           'outage_ms': 1000 * max(b - a for a, b in zip(edges, edges[1:]))}
    if rtts:
        out.update(rtt_mean=st.mean(rtts), rtt_p50=pct(rtts, 50), rtt_p95=pct(rtts, 95),
                   rtt_p99=pct(rtts, 99),
                   jitter_ms=st.mean(abs(a - b) for a, b in zip(rtts, rtts[1:]))
                   if len(rtts) > 1 else 0)
    return out


def read_probe(path):
    with open(path) as f:
        return [(float(r['t_send']), float(r['rtt_ms']) if r['rtt_ms'] else None)
                for r in csv.DictReader(f)]


def read_embb(path):
    """Returns (start time, duration, received Mb/s), or None if the run failed."""
    try:
        d = json.load(open(path))
        return (d['start']['timestamp']['timesecs'], d['start']['test_start']['duration'],
                d['end']['sum_received']['bits_per_second'] / 1e6)
    except (OSError, ValueError, KeyError):
        return None


rows = []
for trial in sorted(glob.glob(os.path.join(ROOT, '*', '*', 'r*'))):
    scen, setup, rep = trial.split(os.sep)[-3:]
    embb = read_embb(os.path.join(trial, 'embb.json'))
    events = []
    try:
        events = [e['event'] for e in json.load(open(os.path.join(trial, 'events.json')))]
    except (OSError, ValueError):
        pass
    common = {'scenario': scen, 'setup': setup, 'rep': rep,
              'protect_on': events.count('PROTECT_ON'), 'protect_off': events.count('PROTECT_OFF'),
              'adjust': events.count('ADJUST'), 'handovers': events.count('HANDOVER')}
    rows.append(dict(common, flow='embb', window='load', kbps=embb[2] * 1000 if embb else None))
    for flow, size in SIZES.get(scen, {}).items():
        path = os.path.join(trial, flow + '.csv')
        if not os.path.exists(path):
            continue
        data = read_probe(path)
        if not data:
            continue
        t0, t1 = data[0][0], data[-1][0]
        if scen == 'handover':
            windows = {'moving': (t0 + 1, t1)}
        elif embb:
            windows = {'idle': (t0 + 3, embb[0]), 'load': (embb[0] + 5, embb[0] + embb[1])}
        else:
            windows = {}
        for name, (lo, hi) in windows.items():
            stats = window_stats(data, lo, hi, size)
            if stats:
                rows.append(dict(common, flow=flow, window=name, **stats))

FIELDS = ['scenario', 'setup', 'rep', 'flow', 'window', 'sent', 'loss_pct', 'kbps', 'rtt_mean',
          'rtt_p50', 'rtt_p95', 'rtt_p99', 'jitter_ms', 'outage_ms', 'protect_on', 'protect_off',
          'adjust', 'handovers']
with open(os.path.join(ROOT, 'trials.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, FIELDS, extrasaction='ignore')
    w.writeheader()
    w.writerows(rows)


def cell(values, digits=1):
    values = [v for v in values if v is not None]
    if not values:
        return '-'
    if len(values) == 1:
        return '%.*f' % (digits, values[0])
    return '%.*f ± %.*f' % (digits, st.mean(values), digits, st.stdev(values))


lines = []
keys = sorted({(r['scenario'], r['flow'], r['window']) for r in rows})
for scen, flow, window in keys:
    lines += ['', '### %s / %s / %s' % (scen, flow, window), '',
              '| Setup | n | Loss % | kb/s | RTT mean ms | RTT p95 ms | RTT p99 ms | Jitter ms | Longest gap ms |',
              '|---|---|---|---|---|---|---|---|---|']
    for setup in SETUPS:
        sel = [r for r in rows if (r['scenario'], r['flow'], r['window'], r['setup']) == (scen, flow, window, setup)]
        if sel:
            get = lambda k: [r.get(k) for r in sel]
            lines.append('| %s | %d | %s | %s | %s | %s | %s | %s | %s |' % (
                setup, len(sel), cell(get('loss_pct'), 2), cell(get('kbps'), 0), cell(get('rtt_mean')),
                cell(get('rtt_p95')), cell(get('rtt_p99')), cell(get('jitter_ms'), 2), cell(get('outage_ms'), 0)))
lines += ['', '### Controller events per trial', '', '| Scenario | Setup | PROTECT_ON | ADJUST | PROTECT_OFF | HANDOVER |', '|---|---|---|---|---|---|']
for scen in sorted({r['scenario'] for r in rows}):
    for setup in SETUPS:
        sel = [r for r in rows if r['scenario'] == scen and r['setup'] == setup and r['flow'] == 'embb']
        if sel:
            lines.append('| %s | %s | %s | %s | %s | %s |' % (scen, setup, cell([r['protect_on'] for r in sel]),
                         cell([r['adjust'] for r in sel]), cell([r['protect_off'] for r in sel]),
                         cell([r['handovers'] for r in sel])))
# results.json for the dashboard: mean, standard deviation and n per group
METRIC_KEYS = ['sent', 'loss_pct', 'kbps', 'rtt_mean', 'rtt_p50', 'rtt_p95', 'rtt_p99', 'jitter_ms', 'outage_ms']
groups = []
for scen, flow, window in keys:
    for setup in SETUPS:
        sel = [r for r in rows if (r['scenario'], r['flow'], r['window'], r['setup']) == (scen, flow, window, setup)]
        if not sel:
            continue
        g = {'scenario': scen, 'flow': flow, 'window': window, 'setup': setup, 'n': len(sel)}
        for k in METRIC_KEYS + ['protect_on', 'adjust', 'protect_off', 'handovers']:
            vals = [r[k] for r in sel if r.get(k) is not None]
            if vals:
                g[k] = {'mean': st.mean(vals), 'sd': st.stdev(vals) if len(vals) > 1 else 0}
        groups.append(g)
reps = max([int(r['rep'][1:]) for r in rows] or [0])
with open(os.path.join(ROOT, 'results.json'), 'w') as f:
    json.dump({'reps': reps, 'groups': groups}, f)

text = '\n'.join(lines) + '\n'
open(os.path.join(ROOT, 'summary.md'), 'w').write(text)
print(text)
