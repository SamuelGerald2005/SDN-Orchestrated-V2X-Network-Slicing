#!/usr/bin/env python3
"""Draws report figures (SVG) from results.json, standard library only.
  figures.py <results.json> <out_dir>
One figure per scenario and measure: a small multiple per flow, one bar per setup,
mean across repeats with a one-standard-deviation whisker."""
import json
import math
import os
import sys

SLICE_COLOR = {'urllc': '#2a78d6', 'platoon': '#eb6834', 'embb': '#1baf7a', 'mmtc': '#eda100'}
SETUPS = [('best_effort', 'Best effort'), ('meters_only', 'Meters only'), ('meters_loop', 'Meters + loop'),
          ('static', 'Static slicing'), ('orchestrated', 'Orchestrated')]
FLOWS = [('urllc_edge', 'URLLC edge'), ('urllc_far', 'URLLC far'), ('platoon', 'Platoon'), ('mmtc', 'mMTC'),
         ('embb', 'eMBB')]
INK, INK2, MUTED, AXIS, GRID = '#0b0b0b', '#52514e', '#898781', '#c3c2b7', '#e1e0d9'


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;')


def fmt(v, unit):
    if unit == 'ms':
        return '%.0f ms' % v if v >= 100 else '%.1f ms' % v if v >= 10 else '%.2f ms' % v
    if unit == '%':
        return '%.2f%%' % v if v < 10 else '%.1f%%' % v
    return '%.1f Mb/s' % (v / 1000) if v >= 1000 else '%.0f kb/s' % v


def panel(x0, y0, w, title, rows, unit, log, color):
    """rows: [(label, mean, sd)]. Returns (svg, height)."""
    out = ['<text x="%d" y="%d" font-size="13" font-weight="bold" fill="%s">%s</text>' % (x0, y0 + 14, INK, esc(title))]
    L, R, rowh, top = 112, 78, 26, y0 + 26
    vals = [m + (s or 0) for _, m, s in rows]
    vmax = max(vals) if vals else 1
    vmin = max(0.1, min(m for _, m, _ in rows) / 2) if log else 0
    use_log = log and vmax / max(vmin, 1e-9) > 20
    topv = 10 ** math.ceil(math.log10(vmax)) if use_log else (vmax * 1.05 or 1)

    def xs(v):
        if use_log:
            return x0 + L + (math.log10(max(v, vmin)) - math.log10(vmin)) / (math.log10(topv) - math.log10(vmin)) * (w - L - R)
        return x0 + L + v / topv * (w - L - R)
    out.append('<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="%s"/>' % (x0 + L, x0 + L, top, top + len(rows) * rowh, AXIS))
    for k, (label, m, sd) in enumerate(rows):
        y = top + k * rowh + 4
        out.append('<text x="%.1f" y="%d" font-size="11" text-anchor="end" fill="%s">%s</text>' % (x0 + L - 8, y + 12, INK2, esc(label)))
        out.append('<rect x="%.1f" y="%d" width="%.1f" height="16" rx="3" fill="%s"/>' % (x0 + L, y, max(2, xs(m) - x0 - L), color))
        end = xs(m)
        if sd:
            a, b = xs(max(vmin if use_log else 0, m - sd)), xs(m + sd)
            out.append('<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="%s" stroke-width="1.5"/>' % (a, b, y + 8, y + 8, INK))
            out.append('<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="%s" stroke-width="1.5"/>' % (b, b, y + 3, y + 13, INK))
            end = max(end, b)
        out.append('<text x="%.1f" y="%d" font-size="11" fill="%s">%s</text>' % (end + 5, y + 12, INK2, fmt(m, unit)))
    h = 26 + len(rows) * rowh + 16
    if use_log:
        out.append('<text x="%d" y="%d" font-size="10" text-anchor="end" fill="%s">log scale</text>' % (x0 + w - 6, y0 + h - 2, MUTED))
    return '\n'.join(out), h


def figure(res, scenario, window, metric, unit, log, title, path, flows=None):
    groups = res['groups']
    panels = []
    for flow, flabel in FLOWS:
        if flows and flow not in flows:
            continue
        key = 'kbps' if flow == 'embb' else metric
        u = 'kb/s' if flow == 'embb' else unit
        rows = []
        for setup, slabel in SETUPS:
            g = next((g for g in groups if g['scenario'] == scenario and g['flow'] == flow and g['setup'] == setup
                      and (g['window'] == window or flow == 'embb')), None)
            if g and g.get(key) and g[key]['mean'] is not None:
                rows.append((slabel, g[key]['mean'], g[key]['sd']))
        if rows:
            panels.append((flabel + (' throughput' if flow == 'embb' else ''), rows, u, log and flow != 'embb',
                           SLICE_COLOR['urllc' if flow.startswith('urllc') else flow]))
    if not panels:
        return False
    cols, W = 2, 900
    pw = W // cols - 10
    parts, heights = [], []
    for i, (t, rows, u, lg, c) in enumerate(panels):
        x, row = (i % cols) * (pw + 20), i // cols
        svg, h = panel(x, 0, pw, t, rows, u, lg, c)
        heights.append((row, h))
        parts.append((row, x, svg))
    rowh = {}
    for row, h in heights:
        rowh[row] = max(rowh.get(row, 0), h)
    offs, acc = {}, 34
    for row in sorted(rowh):
        offs[row] = acc
        acc += rowh[row] + 12
    body = ['<g transform="translate(0,%d)">%s</g>' % (offs[row], svg.replace('x="', 'x="', 1)) for row, x, svg in parts]
    # width/height at twice the viewBox, so a PNG export is sharp enough for print
    out = ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
           'font-family="Liberation Sans, Arial, sans-serif">\n<rect width="100%%" height="100%%" fill="#ffffff"/>\n'
           '<text x="0" y="18" font-size="15" font-weight="bold" fill="%s">%s</text>\n%s\n</svg>\n'
           % (W * 2, acc * 2, W, acc, INK, esc(title), '\n'.join(body)))
    with open(path, 'w') as f:
        f.write(out)
    return True


if __name__ == '__main__':
    res = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    made = []
    specs = [
        ('congestion', 'load', 'rtt_p95', 'ms', True, 'Congestion: 95th percentile RTT during the eMBB flood'),
        ('heavy', 'load', 'rtt_p95', 'ms', True, 'Heavy critical load: 95th percentile RTT during the eMBB flood'),
        ('congestion', 'load', 'loss_pct', '%', False, 'Congestion: packet loss during the eMBB flood'),
        ('heavy', 'load', 'loss_pct', '%', False, 'Heavy critical load: packet loss during the eMBB flood'),
        ('congestion', 'load', 'jitter_ms', 'ms', False, 'Congestion: jitter during the eMBB flood'),
        ('handover', 'moving', 'loss_pct', '%', False, 'Handover: packet loss while vehicles move'),
        ('handover', 'moving', 'outage_ms', 'ms', False, 'Handover: longest delivery gap while vehicles move'),
        ('random', 'load', 'rtt_p95', 'ms', True, 'Random waypoint: 95th percentile RTT during the eMBB flood'),
        ('random', 'load', 'loss_pct', '%', False, 'Random waypoint: packet loss during the eMBB flood'),
    ]
    for scen, win, metric, unit, log, title in specs:
        name = '%s_%s_%s.svg' % (scen, win, metric)
        if figure(res, scen, win, metric, unit, log, title, os.path.join(out, name)):
            made.append(name)
    print('\n'.join(made))
