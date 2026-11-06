#!/usr/bin/env python3
"""Records dashboard frames every 0.5 s into a JSON file the dashboard can replay.
  recorder.py --trace DIR --live DIR --out FILE --dur 100 --setup NAME --scenario NAME"""
import argparse
import json
import os
import time

from frames import FrameBuilder

parser = argparse.ArgumentParser()
parser.add_argument('--trace', required=True)
parser.add_argument('--live', required=True)
parser.add_argument('--out', required=True)
parser.add_argument('--dur', type=float, default=100)
parser.add_argument('--setup', default='')
parser.add_argument('--scenario', default='')
parser.add_argument('--title', default='')
args = parser.parse_args()

builder = FrameBuilder(args.trace, args.live)
frames, start = [], time.time()


def save():
    out = {'title': args.title, 'setup': args.setup, 'scenario': args.scenario,
           'started': start, 'meta': builder.meta(), 'frames': frames}
    tmp = args.out + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(out, f, separators=(',', ':'))
    os.replace(tmp, args.out)


while time.time() - start < args.dur:
    frame = builder.frame()
    frame['t'] = round(frame['t'] - start, 2)
    frames.append(frame)
    if len(frames) % 20 == 0:
        save()
    time.sleep(max(0, 0.5 - (time.time() - start - frame['t'])))
save()
