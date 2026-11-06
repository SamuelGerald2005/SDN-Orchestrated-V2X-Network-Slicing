#!/usr/bin/env python3
"""Draws figures from dashboard recordings (SVG, standard library only).
  run_figures.py <recordings_dir> <out_dir>
  timeline_<a>_vs_<b>.svg : per-second 95th percentile RTT of each probe over a run, one panel per recording
  map_<name>_t<sec>.svg   : where the vehicles are at one moment, and which RSU each is attached to"""
import json
import math
import os
import sys

FLOW = [('urllc_veh1', 'URLLC veh1 → MEC 1', '#2a78d6'), ('urllc_veh4', 'URLLC veh4 → MEC 2', '#7fb0ec'),
        ('platoon', 'Platoon veh2 → veh3', '#eb6834'), ('mmtc', 'mMTC veh6 → telemetry', '#eda100')]
INK, INK2, MUTED, AXIS, GRID = '#0b0b0b', '#52514e', '#898781', '#c3c2b7', '#e1e0d9'
SETUP = {'best_effort': 'Best effort', 'orchestrated': 'Orchestrated', 'static': 'Static slicing'}
FLOOD = (30, 70)          # eMBB flood in the demo recordings (scripts/demo_inner.sh)


def svg(w, h, body, title):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
            'font-family="Liberation Sans, Arial, sans-serif">\n<rect width="100%%" height="100%%" fill="#ffffff"/>\n'
            '<text x="10" y="22" font-size="15" font-weight="bold" fill="%s">%s</text>\n%s\n</svg>\n'
            % (w * 2, h * 2, w, h, INK, title, '\n'.join(body)))


def timeline(recs, path):
    W, ph, L, R = 900, 210, 60, 20
    lo, hi = 0.5, 10000.0
    body = []
    tmax = max(r['frames'][-1]['t'] for r in recs)
    for k, rec in enumerate(recs):
        y0 = 70 + k * (ph + 50)

        def ys(v):
            return y0 + ph - (math.log10(min(max(v, lo), hi)) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * ph

        def xs(t):
            return L + t / tmax * (W - L - R)
        body.append('<text x="10" y="%d" font-size="13" font-weight="bold" fill="%s">%s</text>'
                    % (y0 - 10, INK, SETUP.get(rec['setup'], rec['setup'])))
        body.append('<rect x="%.1f" y="%d" width="%.1f" height="%d" fill="#1baf7a" opacity="0.10"/>'
                    % (xs(FLOOD[0]), y0, xs(FLOOD[1]) - xs(FLOOD[0]), ph))
        body.append('<text x="%.1f" y="%d" font-size="10" fill="%s">eMBB flood</text>' % (xs(FLOOD[0]) + 4, y0 + 12, INK2))
        for v in (1, 10, 100, 1000, 10000):
            body.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="%s"/>' % (L, W - R, ys(v), ys(v), GRID))
            body.append('<text x="%d" y="%.1f" font-size="10" text-anchor="end" fill="%s">%s</text>'
                        % (L - 6, ys(v) + 3, MUTED, ('%g ms' % v) if v < 1000 else '%g s' % (v / 1000)))
        for t in range(0, int(tmax) + 1, 10):
            body.append('<text x="%.1f" y="%d" font-size="10" text-anchor="middle" fill="%s">%d s</text>'
                        % (xs(t), y0 + ph + 14, MUTED, t))
        for flow, _, color in FLOW:
            pts, seg = [], []
            for f in rec['frames']:
                p = (f.get('probes') or {}).get(flow)
                if p and p.get('rtt_p95') is not None and p.get('received'):
                    seg.append('%.1f,%.1f' % (xs(f['t']), ys(p['rtt_p95'])))
                elif seg:
                    pts.append(seg); seg = []
            if seg:
                pts.append(seg)
            for s in pts:
                body.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2" stroke-linejoin="round"/>'
                            % (' '.join(s), color))
    ly = 70 + len(recs) * (ph + 50) - 18
    x = L
    for _, label, color in FLOW:
        body.append('<rect x="%d" y="%d" width="14" height="4" rx="2" fill="%s"/>' % (x, ly - 4, color))
        body.append('<text x="%d" y="%d" font-size="11" fill="%s">%s</text>' % (x + 20, ly, INK2, label))
        x += 30 + 7 * len(label)
    with open(path, 'w') as f:
        f.write(svg(W, ly + 14, body, '95th percentile round-trip time per second, log scale (same vehicles, same flood)'))


if __name__ == '__main__':
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    load = lambda n: json.load(open(os.path.join(src, n + '.json')))
    for a, b in (('scripted_best_effort', 'scripted_orchestrated'), ('random_best_effort', 'random_orchestrated')):
        timeline([load(a), load(b)], os.path.join(out, 'timeline_%s_vs_%s.svg' % (a, b.split('_')[-1])))
    print('\n'.join(sorted(n for n in os.listdir(out) if n.startswith('timeline') and n.endswith('.svg'))))
