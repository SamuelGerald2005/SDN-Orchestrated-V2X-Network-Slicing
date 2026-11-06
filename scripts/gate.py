#!/usr/bin/env python3
"""Decides whether the long experiment run should start: the testbed must come up,
connect, and pass the Step 12 and functional checks. Exit 1 stops the batch."""
import glob
import json
import re
import sys

LOGS = '/app/project/logs'
problems = []
topo = open(LOGS + '/step12/topology.log').read()
results = [int(m) for m in re.findall(r'\((\d+)/90 received\)', topo)]
if not results or results[-1] < 88:
    problems.append('Step 12 pingall results %s (need the last one >= 88/90)' % results)
events = re.findall(r'"event": "(\w+)"', topo)
if events.count('SWITCH') < 3:
    problems.append('only %d switches connected in Step 12' % events.count('SWITCH'))
for log in [LOGS + '/step12/ryu.log', LOGS + '/final/functional/ryu.log']:
    text = open(log).read()
    if 'Traceback' in text or 'OFP ERROR' in text:
        problems.append('errors in ' + log)
try:
    d = json.load(open(LOGS + '/final/functional/limit_urllc_10M.json'))
    rx = d['end']['sum']['bits_per_second'] / 1e6
    if not 3.5 <= rx * (1 - d['end']['sum']['lost_percent'] / 100) <= 6.5 and not 3.5 <= rx <= 6.5:
        problems.append('URLLC meter limit looks wrong: %.2f Mb/s' % rx)
except Exception as e:
    problems.append('URLLC limit test unreadable: %s' % e)
print('GATE ' + ('FAIL: ' + '; '.join(problems) if problems else 'PASS'))
sys.exit(1 if problems else 0)
