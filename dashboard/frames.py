"""Builds one dashboard frame from what a running testbed exposes:
  <trace>/meta.json, <trace>/positions.json   written by v2x_topology_v2.py (V2X_TRACE)
  <live>/<flow>.json                          written by udp_probe.py --live
  RYU REST /v2x/slices and /v2x/events        the orchestrator's northbound API
Shared by recorder.py (saves frames to a file) and server.py (serves them live)."""
import glob
import json
import os
import time
import urllib.request

SLICE_NAMES = ['urllc', 'platoon', 'embb', 'mmtc', 'best_effort']


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def fetch(url, default=None, timeout=1.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return default


def switch_names(meta):
    names = {'1': 's1'}
    for name, rsu in (meta or {}).get('rsus', {}).items():
        names[str(rsu['dpid'])] = name
    return names


class FrameBuilder:
    def __init__(self, trace_dir, live_dir, ryu='http://127.0.0.1:8081'):
        self.trace_dir, self.live_dir, self.ryu = trace_dir, live_dir, ryu
        self.seen = set()
        self.events = []

    def meta(self):
        return read_json(os.path.join(self.trace_dir, 'meta.json'), {})

    def frame(self):
        meta = self.meta()
        names = switch_names(meta)
        pos = read_json(os.path.join(self.trace_dir, 'positions.json'), {})
        status = fetch(self.ryu + '/v2x/slices', {}) or {}
        meter_slice = {str(s.get('meter')): n for n, s in status.get('slices', {}).items()}
        meter_slice[str((status.get('best_effort') or {}).get('meter', 5))] = 'best_effort'
        switches = {}
        for dpid, sw in (status.get('switches') or {}).items():
            installed = {meter_slice.get(str(m), str(m)): v
                         for m, v in (sw.get('installed_kbps') or {}).items()}
            switches[names.get(dpid, dpid)] = {
                'measured': sw.get('measured_kbps') or {},
                'installed': installed,
                'protecting': sw.get('protecting_critical', False)}
        probes = {}
        for path in glob.glob(os.path.join(self.live_dir, '*.json')):
            p = read_json(path)
            if p:
                probes[p.get('flow') or os.path.basename(path)[:-5]] = p
        new = []
        for e in fetch(self.ryu + '/v2x/events', []) or []:
            key = (e.get('t'), e.get('event'), e.get('detail'))
            if key not in self.seen:
                self.seen.add(key)
                new.append(e)
        self.events.extend(new)
        return {'t': round(time.time(), 2),
                'vehicles': pos.get('vehicles', {}),
                'switches': switches,
                'probes': probes,
                'events': new,
                'config': {k: status.get(k) for k in ('slicing_enabled', 'priority_enabled',
                                                      'dynamic_enabled', 'policy')},
                'budgets': {n: s.get('budget_kbps') for n, s in status.get('slices', {}).items()}}
